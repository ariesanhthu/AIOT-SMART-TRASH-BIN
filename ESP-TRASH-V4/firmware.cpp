#include "firmware.h"

#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>

#include <cinttypes>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>

#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "img_converters.h"

#include "camera_adapter.h"
#include "camera_web_server.h"
#include "cloud_sync.h"
#include "image_preprocessor.h"
#include "model_data.h"
#include "network_config.h"
#include "status.h"
#include "tflm_classifier.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#ifndef CLOUDINARY_CLOUD_NAME
#define CLOUDINARY_CLOUD_NAME ""
#endif

#ifndef CLOUDINARY_UPLOAD_PRESET
#define CLOUDINARY_UPLOAD_PRESET ""
#endif

namespace aiot
{
  namespace
  {

    // UART2 is reserved for the Arduino Nano. UART0 remains available for logs and
    // flashing through the USB-to-serial adapter.
    HardwareSerial g_nano_serial(2);

    constexpr std::uint32_t kDebugBaud = 115200;
    constexpr std::uint32_t kNanoBaud = 9600;
    constexpr int kNanoRxPin = 13; // Nano TX -> voltage divider -> ESP32 GPIO13.
    constexpr int kNanoTxPin = 14; // ESP32 GPIO14 -> Nano RX.
    constexpr std::size_t kNanoRxBufferBytes = 128;
    constexpr std::size_t kNanoCommandBufferBytes = 32;
    constexpr unsigned long kCaptureRetryDelayMs = 30;
    constexpr std::size_t kMonitorCommandBufferBytes = 24;
    constexpr std::size_t kModelInputBytes =
        static_cast<std::size_t>(model_contract::kInputHeight) *
        static_cast<std::size_t>(model_contract::kInputWidth) *
        static_cast<std::size_t>(model_contract::kInputChannels);
    // Application-level rejection policy. This is intentionally outside the
    // model/TFLite contract and is applied only after inference.
    constexpr float kRecognitionConfidenceThreshold = 0.60F;

    enum class WifiState : std::uint8_t
    {
      kIdle,
      kConnectingStored,
      kConnected,
      kOffline,
    };

    // This is the wire protocol expected by the Nano. It intentionally differs
    // from the model label indices (paper=0, plastic=1, organic=2).
    enum class NanoResult : std::uint8_t
    {
      kNotRecognized = 0,
      kPlastic = 1,
      kPaper = 2,
      kOrganic = 3,
    };

    enum class ServerSyncResult : std::uint8_t
    {
      kSuccess,
      kWifiUnavailable,
      kNoJpeg,
      kInvalidUrl,
      kConnectFailed,
      kWriteFailed,
      kHttpFailed,
      kFillTimeout,
    };

    struct RecognitionTelemetry
    {
      std::uint8_t *jpeg_data = nullptr;
      std::size_t jpeg_length = 0;
      unsigned frame_width = 0;
      unsigned frame_height = 0;
      unsigned frame_length = 0;
      ClassificationResult classification{};
      bool has_inference_result = false;

      ~RecognitionTelemetry()
      {
        if (jpeg_data != nullptr)
        {
          std::free(jpeg_data);
          jpeg_data = nullptr;
        }
      }

      RecognitionTelemetry() = default;
      RecognitionTelemetry(const RecognitionTelemetry &) = delete;
      RecognitionTelemetry &operator=(const RecognitionTelemetry &) = delete;
    };

    struct HttpEndpoint
    {
      char host[64]{};
      char path[128]{};
      std::uint16_t port = 80;
    };

    struct LocalDashboardConfig
    {
      std::uint8_t plastic_threshold = 59;
      std::uint8_t paper_threshold = 59;
      std::uint8_t organic_threshold = 59;
      bool maintenance_mode = false;
      bool loaded = false;
    };

    TflmClassifier g_classifier;
    ImagePreprocessor g_preprocessor;
    CameraAdapter g_camera;
    bool g_ready = false;
    bool g_camera_web_ready = false;
    bool g_mdns_ready = false;
    bool g_nano_transaction_active = false;
    volatile WifiState g_wifi_state = WifiState::kIdle;
    std::uint32_t g_last_camera_service_attempt_ms = 0;
    std::uint32_t g_last_nano_ready_response_ms = 0;
    std::uint32_t g_last_wifi_reconnect_attempt_ms = 0;
    std::uint32_t g_capture_sequence = 0;
    std::uint32_t g_previous_raw_frame_hash = 0;
    std::uint32_t g_previous_input_hash = 0;
    bool g_has_previous_capture_hash = false;
    CompartmentFillLevels g_fill_levels;
    LocalDashboardConfig g_dashboard_config;

    constexpr std::uint32_t kCameraServiceRetryIntervalMs = 5000;
    constexpr std::uint32_t kNanoReadyResponseMinIntervalMs = 500;
    constexpr std::uint32_t kWifiReconnectIntervalMs = 15000;

    std::uint32_t FingerprintFNV1a(const void *const data,
                                   const std::size_t bytes)
    {
      const auto *cursor = static_cast<const std::uint8_t *>(data);
      const auto *const end = cursor + bytes;
      std::uint32_t hash = 2166136261U;
      while (cursor != end)
      {
        hash ^= *cursor++;
        hash *= 16777619U;
      }
      return hash;
    }

    std::uint64_t FrameTimestampUs(const camera_fb_t &frame)
    {
      return static_cast<std::uint64_t>(frame.timestamp.tv_sec) * 1000000ULL +
             static_cast<std::uint64_t>(frame.timestamp.tv_usec);
    }

    void LogMemory(const char *const stage)
    {
      Serial.printf(
          "[%s] internal free/largest: %u/%u bytes; PSRAM free/largest: "
          "%u/%u bytes\n",
          stage,
          static_cast<unsigned>(
              heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
          static_cast<unsigned>(heap_caps_get_largest_free_block(
              MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
          static_cast<unsigned>(
              heap_caps_get_free_size(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)),
          static_cast<unsigned>(heap_caps_get_largest_free_block(
              MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)));
    }

    bool ParseNanoTrigger(const char *const command)
    {
      unsigned trigger = 0;
      char extra = '\0';
      return command != nullptr &&
             std::sscanf(command, "T %u %c", &trigger, &extra) == 1 &&
             trigger == 1U;
    }

    bool ParseNanoReadyProbe(const char *const command)
    {
      return command != nullptr && std::strcmp(command, "H 1") == 0;
    }

    void SendNanoMessage(const char *const prefix, const unsigned value)
    {
      g_nano_serial.print(prefix);
      g_nano_serial.print(' ');
      g_nano_serial.println(value);
      g_nano_serial.flush();
    }

    void SendNanoAck(const char command_type)
    {
      g_nano_serial.print("A ");
      g_nano_serial.println(command_type);
      g_nano_serial.flush();
    }

    void SendNanoConfig()
    {
      g_nano_serial.print("G ");
      g_nano_serial.print(static_cast<unsigned>(
          g_dashboard_config.plastic_threshold));
      g_nano_serial.print(' ');
      g_nano_serial.print(static_cast<unsigned>(
          g_dashboard_config.paper_threshold));
      g_nano_serial.print(' ');
      g_nano_serial.print(static_cast<unsigned>(
          g_dashboard_config.organic_threshold));
      g_nano_serial.print(' ');
      g_nano_serial.println(g_dashboard_config.maintenance_mode ? 1 : 0);
      g_nano_serial.flush();
      Serial.printf("Config sent to Nano: plastic=%u paper=%u organic=%u "
                    "maintenance=%u\n",
                    static_cast<unsigned>(
                        g_dashboard_config.plastic_threshold),
                    static_cast<unsigned>(g_dashboard_config.paper_threshold),
                    static_cast<unsigned>(
                        g_dashboard_config.organic_threshold),
                    g_dashboard_config.maintenance_mode ? 1U : 0U);
    }

    bool SendNanoReadyState()
    {
      const std::uint32_t now = millis();
      if (g_last_nano_ready_response_ms != 0U &&
          now - g_last_nano_ready_response_ms <
              kNanoReadyResponseMinIntervalMs)
      {
        return false;
      }
      g_last_nano_ready_response_ms = now;
      SendNanoMessage("R", g_nano_transaction_active ? 0U : 1U);
      return true;
    }

    const char *ServerSyncResultName(const ServerSyncResult result)
    {
      switch (result)
      {
      case ServerSyncResult::kSuccess:
        return "OK";
      case ServerSyncResult::kWifiUnavailable:
        return "WIFI";
      case ServerSyncResult::kNoJpeg:
        return "NO_JPEG";
      case ServerSyncResult::kInvalidUrl:
        return "URL";
      case ServerSyncResult::kConnectFailed:
        return "CONNECT";
      case ServerSyncResult::kWriteFailed:
        return "WRITE";
      case ServerSyncResult::kHttpFailed:
        return "HTTP";
      case ServerSyncResult::kFillTimeout:
        return "FILL_TIMEOUT";
      }
      return "UNKNOWN";
    }

    void FinishNanoTransaction(const ServerSyncResult result)
    {
      g_nano_transaction_active = false;
      const bool server_synced = result == ServerSyncResult::kSuccess;
      if (!server_synced)
      {
        g_nano_serial.print("E ");
        g_nano_serial.println(ServerSyncResultName(result));
        g_nano_serial.flush();
      }
      SendNanoMessage("D", server_synced ? 1U : 0U);
      Serial.printf("Nano transaction finished: local-server=%s (%s)\n",
                    server_synced ? "ok" : "failed",
                    ServerSyncResultName(result));
    }

    bool ParseNanoFillLevels(const char *const command,
                             CompartmentFillLevels *const levels)
    {
      if (command == nullptr || levels == nullptr)
      {
        return false;
      }

      unsigned plastic = 0;
      unsigned paper = 0;
      unsigned organic = 0;
      char extra = '\0';
      if (std::sscanf(command, "F %u %u %u %c", &plastic, &paper,
                      &organic, &extra) != 3 ||
          plastic > 100U || paper > 100U || organic > 100U)
      {
        return false;
      }

      levels->plastic = static_cast<std::uint8_t>(plastic);
      levels->paper = static_cast<std::uint8_t>(paper);
      levels->organic = static_cast<std::uint8_t>(organic);
      levels->received = true;
      return true;
    }

    bool HandleNanoCommandLine(const char *const command)
    {
      if (ParseNanoReadyProbe(command))
      {
        if (SendNanoReadyState())
        {
          Serial.printf("Nano ready probe -> R %u\n",
                        g_nano_transaction_active ? 0U : 1U);
        }
        return false;
      }

      if (ParseNanoTrigger(command))
      {
        // ACK is sent before camera/inference so the Nano can distinguish an
        // accepted trigger from a disconnected UART. Repeated T 1 is ACKed but
        // does not start a second capture while this transaction is active.
        SendNanoAck('T');
        if (g_nano_transaction_active)
        {
          Serial.println("Duplicate Nano trigger ACKed and ignored");
          return false;
        }
        g_nano_transaction_active = true;
        return true;
      }

      CompartmentFillLevels levels;
      if (ParseNanoFillLevels(command, &levels))
      {
        if (!g_nano_transaction_active)
        {
          Serial.println("Orphan fill packet received without active capture; returning D 0");
          SendNanoMessage("D", 0U);
          return false;
        }
        g_fill_levels = levels;
        SendNanoAck('F');
        Serial.printf(
            "Nano fill levels plastic=%u paper=%u organic=%u\n",
            static_cast<unsigned>(g_fill_levels.plastic),
            static_cast<unsigned>(g_fill_levels.paper),
            static_cast<unsigned>(g_fill_levels.organic));
        return false;
      }

      Serial.printf("Invalid Nano command ignored [%s]\n", command);
      return false;
    }

    bool ReadNanoCaptureCommand()
    {
      static char command[kNanoCommandBufferBytes]{};
      static std::size_t command_length = 0;
      bool capture_requested = false;

      while (g_nano_serial.available() > 0)
      {
        const int received = g_nano_serial.read();
        if (received == '\r' || received == '\n')
        {
          if (command_length > 0U)
          {
            command[command_length] = '\0';
            capture_requested =
                HandleNanoCommandLine(command) || capture_requested;
          }
          command_length = 0;
          command[0] = '\0';
          continue;
        }

        if (received < 32 || received > 126)
        {
          command_length = 0;
          command[0] = '\0';
          continue;
        }

        if (command_length + 1U >= sizeof(command))
        {
          command_length = 0;
          command[0] = '\0';
          Serial.println("Nano command too long; ignored");
          continue;
        }

        command[command_length++] = static_cast<char>(received);
        command[command_length] = '\0';
      }

      return capture_requested;
    }

    NanoResult ToNanoResult(const model_contract::WasteClass waste_class)
    {
      switch (waste_class)
      {
      case model_contract::WasteClass::kPaper:
        return NanoResult::kPaper;
      case model_contract::WasteClass::kPlastic:
        return NanoResult::kPlastic;
      case model_contract::WasteClass::kOrganic:
        return NanoResult::kOrganic;
      case model_contract::WasteClass::kInvalid:
        return NanoResult::kNotRecognized;
      }
      return NanoResult::kNotRecognized;
    }

    bool WaitForNanoFillLevels()
    {
      const std::uint32_t started_at = millis();
      while (millis() - started_at < network_config::kNanoFillTimeoutMs)
      {
        ReadNanoCaptureCommand();
        if (g_fill_levels.received)
        {
          return true;
        }
        delay(2);
      }
      Serial.println("Timed out waiting for Nano fill levels (F p pa o)");
      return false;
    }

    void WarmUpCamera()
    {
      // Discard early frames so auto exposure and auto white balance can settle.
      for (int index = 0; index < 2; ++index)
      {
        Status status = Status::kOk;
        CameraFrameLease frame = g_camera.Capture(&status);
        if (!frame || status != Status::kOk)
        {
          Serial.printf("Camera warm-up %d failed: %s\n", index + 1,
                        StatusName(status));
        }
        delay(40);
      }
    }

    const char *WifiStateName(const WifiState state)
    {
      switch (state)
      {
      case WifiState::kIdle:
        return "idle";
      case WifiState::kConnectingStored:
        return "connecting_stored";
      case WifiState::kConnected:
        return "connected";
      case WifiState::kOffline:
        return "offline";
      }
      return "unknown";
    }

    void SetWifiState(const WifiState state)
    {
      if (g_wifi_state == state)
      {
        return;
      }
      g_wifi_state = state;
      Serial.printf("Wi-Fi state: %s\n", WifiStateName(state));
    }

    bool HasConfiguredWifi()
    {
      return WIFI_SSID[0] != '\0';
    }

    bool InitializeWifi()
    {
      // Flash persistence keeps credentials supplied by secrets.h or an older
      // provisioning build available across restarts.
      WiFi.persistent(true);
      WiFi.mode(WIFI_STA);
      WiFi.setHostname(network_config::kMdnsHostname);
      WiFi.setSleep(false);
      WiFi.setAutoReconnect(true);
      // The hotspot is nearby; lower RF power reduces ESP32-CAM current peaks
      // while servos are connected without sacrificing LAN range here.
      WiFi.setTxPower(WIFI_POWER_8_5dBm);

      if (WiFi.status() == WL_CONNECTED)
      {
        SetWifiState(WifiState::kConnected);
        return true;
      }

      // Bat dau ket noi nhung khong cho. UART, camera va AI phai san sang ngay
      // ca khi router khong ton tai.
      SetWifiState(WifiState::kConnectingStored);
      if (HasConfiguredWifi())
      {
        Serial.println("Starting Wi-Fi with secrets.h credentials (non-blocking)");
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      }
      else
      {
        Serial.println("Starting Wi-Fi with stored credentials (non-blocking)");
        WiFi.begin();
      }
      g_last_wifi_reconnect_attempt_ms = millis();
      return WiFi.status() == WL_CONNECTED;
    }

    void MaintainWifiConnection()
    {
      if (WiFi.status() == WL_CONNECTED)
      {
        SetWifiState(WifiState::kConnected);
        return;
      }

      const std::uint32_t now = millis();
      if (now - g_last_wifi_reconnect_attempt_ms < kWifiReconnectIntervalMs)
      {
        return;
      }

      g_last_wifi_reconnect_attempt_ms = now;
      SetWifiState(WifiState::kOffline);
      Serial.println("Wi-Fi offline; reconnect requested in background");
      WiFi.reconnect();
    }

    bool EnsureWifiConnectedForUpload()
    {
      if (WiFi.status() == WL_CONNECTED)
      {
        return true;
      }

      Serial.printf("Wi-Fi unavailable at upload; waiting up to %" PRIu32
                    " ms for reconnect\n",
                    network_config::kReconnectTimeoutMs);
      WiFi.reconnect();
      const std::uint32_t started_at = millis();
      while (WiFi.status() != WL_CONNECTED &&
             millis() - started_at < network_config::kReconnectTimeoutMs)
      {
        delay(100);
      }

      if (WiFi.status() != WL_CONNECTED)
      {
        SetWifiState(WifiState::kOffline);
        return false;
      }
      SetWifiState(WifiState::kConnected);
      Serial.printf("Wi-Fi restored before upload: IP=%s RSSI=%d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
    }

    bool ConfirmInitialWifiConnectivity()
    {
      const std::uint32_t wifi_started_ms = millis();
      Serial.printf("Waiting up to %" PRIu32 " ms for initial Wi-Fi connection\n",
                    network_config::kInitialWifiTimeoutMs);
      while (WiFi.status() != WL_CONNECTED &&
             millis() - wifi_started_ms <
                 network_config::kInitialWifiTimeoutMs)
      {
        delay(250);
      }

      if (WiFi.status() != WL_CONNECTED)
      {
        SetWifiState(WifiState::kOffline);
        Serial.println(
            "Initial Wi-Fi confirmation timed out; reconnect continues in background");
        return false;
      }

      SetWifiState(WifiState::kConnected);
      Serial.printf("Initial Wi-Fi confirmed: IP=%s gateway=%s RSSI=%d dBm\n",
                    WiFi.localIP().toString().c_str(),
                    WiFi.gatewayIP().toString().c_str(), WiFi.RSSI());

      // Do not probe or wait for the Python server during boot. Connectivity
      // is checked only when a completed recognition is ready to upload.
      return true;
    }

    void MaintainCameraWebServices()
    {
      if (!g_ready)
      {
        return;
      }

      const std::uint32_t now = millis();
      const bool retry_due =
          g_last_camera_service_attempt_ms == 0 ||
          now - g_last_camera_service_attempt_ms >=
              kCameraServiceRetryIntervalMs;
      if (!retry_due)
      {
        return;
      }
      g_last_camera_service_attempt_ms = now;

      if (!g_camera_web_ready)
      {
        g_camera_web_ready = StartCameraWebServer(&g_camera);
      }

      if (WiFi.status() == WL_CONNECTED && !g_mdns_ready)
      {
        g_mdns_ready = MDNS.begin(network_config::kMdnsHostname);
        if (g_mdns_ready)
        {
          MDNS.addService("http", "tcp", 80);
          Serial.printf("Camera capture: http://%s.local/capture\n",
                        network_config::kMdnsHostname);
          Serial.printf("Camera stream:  http://%s.local:81/stream\n",
                        network_config::kMdnsHostname);
          Serial.printf("Camera IP:      http://%s/capture\n",
                        WiFi.localIP().toString().c_str());
        }
        else
        {
          Serial.println("Camera mDNS start failed; use the printed ESP32 IP");
        }
      }
    }

    void ResetWifiCredentialsAndRestart()
    {
      Serial.println("WIFI_RESET received: erasing stored Wi-Fi credentials");
      const bool erased = WiFi.disconnect(true, true, 1000);
      Serial.println(erased ? "Wi-Fi credentials erased"
                            : "Wi-Fi erase reported an error; restarting");
      Serial.println("Restarting; Wi-Fi will use credentials from secrets.h");
      Serial.flush();
      delay(200);
      ESP.restart();
      delay(1000);
    }

    bool ReadMonitorCaptureCommand()
    {
      static char command[kMonitorCommandBufferBytes]{};
      static std::size_t command_length = 0;
      bool capture_requested = false;

      while (Serial.available() > 0)
      {
        const int received = Serial.read();
        if (received == 1 ||
            (received == '1' && command_length == 0U))
        {
          capture_requested = true;
          continue;
        }

        if (received == '\r' || received == '\n')
        {
          if (command_length > 0U)
          {
            if (std::strcmp(command, "T 1") == 0)
            {
              capture_requested = true;
            }
            else
            {
              CompartmentFillLevels levels;
              if (ParseNanoFillLevels(command, &levels))
              {
                g_fill_levels = levels;
                Serial.printf(
                    "Monitor fill levels plastic=%u paper=%u organic=%u\n",
                    static_cast<unsigned>(g_fill_levels.plastic),
                    static_cast<unsigned>(g_fill_levels.paper),
                    static_cast<unsigned>(g_fill_levels.organic));
              }
              else if (std::strcmp(command, "WIFI_RESET") != 0)
              {
                Serial.printf("Invalid Monitor command ignored [%s]\n",
                              command);
              }
            }
          }
          command_length = 0;
          command[0] = '\0';
          continue;
        }

        if (received < 32 || received > 126)
        {
          continue;
        }

        if (command_length + 1U >= sizeof(command))
        {
          command_length = 0;
          command[0] = '\0';
          Serial.println("Serial command too long; ignored");
          continue;
        }

        command[command_length++] = static_cast<char>(received);
        command[command_length] = '\0';
        if (std::strcmp(command, "WIFI_RESET") == 0)
        {
          ResetWifiCredentialsAndRestart();
        }
      }

      return capture_requested;
    }

    bool WaitForMonitorFillLevels()
    {
      Serial.println(
          "Enter F <plastic> <paper> <organic> to upload to local server");
      const std::uint32_t started_at = millis();
      while (millis() - started_at < network_config::kMonitorFillTimeoutMs)
      {
        ReadMonitorCaptureCommand();
        if (g_fill_levels.received)
        {
          return true;
        }
        delay(2);
      }
      Serial.println("Monitor fill-level timeout; local server upload cancelled");
      return false;
    }

    bool EncodeTelemetryJpeg(camera_fb_t *const frame,
                             RecognitionTelemetry *const telemetry)
    {
      if (frame == nullptr || telemetry == nullptr)
      {
        return false;
      }

      const bool encoded =
          frame2jpg(frame, network_config::kTelemetryJpegQuality,
                    &telemetry->jpeg_data, &telemetry->jpeg_length);
      if (!encoded || telemetry->jpeg_data == nullptr ||
          telemetry->jpeg_length == 0U)
      {
        if (telemetry->jpeg_data != nullptr)
        {
          std::free(telemetry->jpeg_data);
        }
        telemetry->jpeg_data = nullptr;
        telemetry->jpeg_length = 0U;
        Serial.println("RGB565-to-JPEG conversion failed; upload skipped");
        return false;
      }
      return true;
    }

    NanoResult CaptureAndClassify(RecognitionTelemetry *const telemetry)
    {
      if (telemetry == nullptr || !g_ready)
      {
        Serial.println("Request rejected: AI pipeline is not ready");
        return NanoResult::kNotRecognized;
      }

      Status status = Status::kOk;
      TfLiteTensor *const input = g_classifier.input_tensor();
      if (input == nullptr || input->data.int8 == nullptr)
      {
        Serial.println("Inference input tensor is unavailable");
        return NanoResult::kNotRecognized;
      }

      const std::uint32_t sequence = ++g_capture_sequence;
      const std::uint32_t trigger_received_ms = millis();
      Serial.printf(
          "Capture #%" PRIu32 ": trigger accepted; settle=%" PRIu32
          " ms, queued frames to discard=%u\n",
          sequence, network_config::kTriggerToCaptureDelayMs,
          static_cast<unsigned>(network_config::kFreshCaptureDiscardFrames));
      delay(network_config::kTriggerToCaptureDelayMs);
      // A frame queued before this point is not allowed to reach preprocessing.
      // CaptureFresh returns such a buffer to the driver and waits for a frame
      // whose camera timestamp proves it was captured after this boundary.
      const std::uint64_t fresh_frame_not_before_us =
          static_cast<std::uint64_t>(esp_timer_get_time());

      std::uint32_t raw_frame_hash = 0U;
      std::uint32_t input_hash = 0U;
      std::uint64_t frame_timestamp_us = 0U;
      std::uint64_t frame_age_us = 0U;

      {
        CameraFrameLease frame = g_camera.CaptureFresh(
            &status, network_config::kFreshCaptureDiscardFrames,
            fresh_frame_not_before_us);
        if (!frame || status != Status::kOk)
        {
          // One short retry handles an occasional transient frame-buffer miss.
          delay(kCaptureRetryDelayMs);
          frame = g_camera.CaptureFresh(
              &status, network_config::kFreshCaptureDiscardFrames,
              fresh_frame_not_before_us);
        }
        if (!frame || status != Status::kOk)
        {
          Serial.printf("Capture failed: %s\n", StatusName(status));
          return NanoResult::kNotRecognized;
        }

        telemetry->frame_width = frame.get()->width;
        telemetry->frame_height = frame.get()->height;
        telemetry->frame_length = frame.get()->len;
        frame_timestamp_us = FrameTimestampUs(*frame.get());
        const std::uint64_t now_us =
            static_cast<std::uint64_t>(esp_timer_get_time());
        frame_age_us = now_us >= frame_timestamp_us
                           ? now_us - frame_timestamp_us
                           : 0U;
        raw_frame_hash =
            FingerprintFNV1a(frame.get()->buf, frame.get()->len);

        ImageView view{};
        status = CameraAdapter::MakeImageView(*frame.get(), &view);
        if (status == Status::kOk)
        {
          status = g_preprocessor.Run(view, input->data.int8, input->bytes);
          if (status == Status::kOk)
          {
            input_hash = FingerprintFNV1a(input->data.int8, kModelInputBytes);
          }
        }

        // Encode the same frame used by AI. The JPEG survives after the raw camera
        // framebuffer is returned, so Invoke() and HTTP never hold that buffer.
        EncodeTelemetryJpeg(frame.get(), telemetry);
      }

      if (status != Status::kOk)
      {
        Serial.printf("Image preprocessing failed: %s\n", StatusName(status));
        return NanoResult::kNotRecognized;
      }

      const bool same_raw_frame =
          g_has_previous_capture_hash &&
          raw_frame_hash == g_previous_raw_frame_hash;
      const bool same_model_input =
          g_has_previous_capture_hash && input_hash == g_previous_input_hash;
      Serial.printf(
          "Capture #%" PRIu32 ": trigger_to_frame=%" PRIu32
          "ms frame_ts=%" PRIu64 "us frame_age=%" PRIu64
          "us raw_hash=%08" PRIx32 " input_hash=%08" PRIx32
          " same_raw=%s same_input=%s\n",
          sequence, millis() - trigger_received_ms, frame_timestamp_us,
          frame_age_us, raw_frame_hash, input_hash,
          same_raw_frame ? "YES" : "no",
          same_model_input ? "YES" : "no");
      if (same_raw_frame || same_model_input)
      {
        Serial.println(
            "WARNING: exact capture/input fingerprint repeated from previous "
            "inference; inspect the uploaded JPEGs");
      }
      g_previous_raw_frame_hash = raw_frame_hash;
      g_previous_input_hash = input_hash;
      g_has_previous_capture_hash = true;

      status = g_classifier.Classify(&telemetry->classification);
      if (status != Status::kOk)
      {
        Serial.printf("Inference failed: %s\n", StatusName(status));
        return NanoResult::kNotRecognized;
      }
      const ClassificationResult &result = telemetry->classification;
      telemetry->has_inference_result = true;
      if (result.confidence < kRecognitionConfidenceThreshold)
      {
        Serial.printf(
            "Khong nhan dien duoc: confidence %.4f < threshold %.2f; "
            "p=[paper %.4f, plastic %.4f, organic %.4f] -> C 0\n",
            static_cast<double>(result.confidence),
            static_cast<double>(kRecognitionConfidenceThreshold),
            static_cast<double>(result.probabilities[0]),
            static_cast<double>(result.probabilities[1]),
            static_cast<double>(result.probabilities[2]));
        return NanoResult::kNotRecognized;
      }

      const NanoResult nano_result = ToNanoResult(result.predicted);
      Serial.printf(
          "Frame=%ux%u/%uB JPEG=%uB class=%s confidence=%.4f "
          "p=[paper %.4f, plastic %.4f, organic %.4f] inference=%" PRId64
          " us -> Nano=%u\n",
          telemetry->frame_width, telemetry->frame_height,
          telemetry->frame_length,
          static_cast<unsigned>(telemetry->jpeg_length),
          ClassName(result.predicted), static_cast<double>(result.confidence),
          static_cast<double>(result.probabilities[0]),
          static_cast<double>(result.probabilities[1]),
          static_cast<double>(result.probabilities[2]), result.inference_time_us,
          static_cast<unsigned>(nano_result));

      return nano_result;
    }

    bool ParseHttpEndpoint(const char *const url, HttpEndpoint *const endpoint)
    {
      if (url == nullptr || endpoint == nullptr)
      {
        return false;
      }

      constexpr char kScheme[] = "http://";
      constexpr std::size_t kSchemeLength = sizeof(kScheme) - 1U;
      if (std::strncmp(url, kScheme, kSchemeLength) != 0)
      {
        return false;
      }

      const char *const host_begin = url + kSchemeLength;
      const char *const path_begin = std::strchr(host_begin, '/');
      const char *const host_end =
          path_begin != nullptr ? path_begin : host_begin + std::strlen(host_begin);
      const char *port_begin = nullptr;
      for (const char *cursor = host_begin; cursor < host_end; ++cursor)
      {
        if (*cursor == ':')
        {
          port_begin = cursor;
          break;
        }
      }

      const char *const host_stop =
          port_begin != nullptr ? port_begin : host_end;
      const std::size_t host_length =
          static_cast<std::size_t>(host_stop - host_begin);
      if (host_length == 0U || host_length >= sizeof(endpoint->host))
      {
        return false;
      }
      std::memcpy(endpoint->host, host_begin, host_length);
      endpoint->host[host_length] = '\0';

      endpoint->port = 80;
      if (port_begin != nullptr)
      {
        const std::size_t port_length =
            static_cast<std::size_t>(host_end - port_begin - 1);
        if (port_length == 0U || port_length > 5U)
        {
          return false;
        }

        char port_text[6]{};
        std::memcpy(port_text, port_begin + 1, port_length);
        char *parse_end = nullptr;
        const unsigned long parsed_port = std::strtoul(port_text, &parse_end, 10);
        if (parse_end == nullptr || *parse_end != '\0' ||
            parsed_port == 0UL || parsed_port > 65535UL)
        {
          return false;
        }
        endpoint->port = static_cast<std::uint16_t>(parsed_port);
      }

      const char *const path_text = path_begin != nullptr ? path_begin : "/";
      if (std::strlen(path_text) >= sizeof(endpoint->path))
      {
        return false;
      }
      std::strcpy(endpoint->path, path_text);
      return true;
    }

    void AddUnsignedHeader(WiFiClient *const client, const char *const name,
                           const unsigned long value)
    {
      client->printf("%s: %lu\r\n", name, value);
    }

    void AddInt64Header(WiFiClient *const client, const char *const name,
                        const std::int64_t value)
    {
      client->printf("%s: %" PRId64 "\r\n", name, value);
    }

    void AddFloatHeader(WiFiClient *const client, const char *const name,
                        const float value)
    {
      client->printf("%s: %.6f\r\n", name, static_cast<double>(value));
    }

    bool ReadHttpLineUntil(WiFiClient *const client, String *const line,
                           const std::uint32_t started_at)
    {
      if (client == nullptr || line == nullptr)
      {
        return false;
      }
      line->remove(0);
      while (millis() - started_at < network_config::kHttpResponseTimeoutMs)
      {
        while (client->available() > 0)
        {
          const int value = client->read();
          if (value < 0)
          {
            break;
          }
          if (value == '\n')
          {
            line->trim();
            return true;
          }
          if (value != '\r')
          {
            *line += static_cast<char>(value);
          }
        }
        if (!client->connected())
        {
          line->trim();
          return line->length() > 0;
        }
        delay(1);
      }
      return false;
    }

    int ReadHttpResponseCode(WiFiClient *const client, char *const body_preview,
                             const std::size_t body_preview_size)
    {
      if (client == nullptr)
      {
        return -1;
      }

      const std::uint32_t started_at = millis();
      String status_line;
      if (!ReadHttpLineUntil(client, &status_line, started_at))
      {
        return -1;
      }
      int response_code = -1;
      if (status_line.startsWith("HTTP/"))
      {
        const int first_space = status_line.indexOf(' ');
        if (first_space >= 0)
        {
          response_code = status_line.substring(first_space + 1).toInt();
        }
      }

      String header_line;
      while (ReadHttpLineUntil(client, &header_line, started_at))
      {
        if (header_line.length() == 0)
        {
          break;
        }
      }

      // The local server persists the JPEG before returning 201. For a
      // successful response there is no reason to wait for or buffer its JSON
      // body: return immediately so Nano receives D 1 without extra delay.
      if (response_code >= 200 && response_code < 300)
      {
        if (body_preview != nullptr && body_preview_size > 0U)
        {
          body_preview[0] = '\0';
        }
        return response_code;
      }

      if (body_preview != nullptr && body_preview_size > 0U)
      {
        std::size_t length = 0;
        while ((client->connected() || client->available() > 0) &&
               millis() - started_at < network_config::kHttpResponseTimeoutMs)
        {
          while (client->available() > 0)
          {
            const char value = static_cast<char>(client->read());
            if (length + 1U < body_preview_size)
            {
              body_preview[length++] = value;
            }
          }
          if (!client->connected())
          {
            break;
          }
          delay(1);
        }
        body_preview[length] = '\0';
      }

      return response_code;
    }

    int ReadHttpResponseBody(WiFiClient *const client, String *const body,
                             const std::size_t max_body_size)
    {
      if (client == nullptr || body == nullptr)
      {
        return -1;
      }

      body->remove(0);
      const std::uint32_t started_at = millis();
      String status_line;
      if (!ReadHttpLineUntil(client, &status_line, started_at))
      {
        return -1;
      }

      int response_code = -1;
      if (status_line.startsWith("HTTP/"))
      {
        const int first_space = status_line.indexOf(' ');
        if (first_space >= 0)
        {
          response_code = status_line.substring(first_space + 1).toInt();
        }
      }

      String header_line;
      while (ReadHttpLineUntil(client, &header_line, started_at))
      {
        if (header_line.length() == 0)
        {
          break;
        }
      }

      while ((client->connected() || client->available() > 0) &&
             millis() - started_at < network_config::kHttpResponseTimeoutMs)
      {
        while (client->available() > 0)
        {
          const char value = static_cast<char>(client->read());
          if (body->length() < max_body_size)
          {
            *body += value;
          }
        }
        if (!client->connected())
        {
          break;
        }
        delay(1);
      }
      return response_code;
    }

    bool ExtractJsonNumber(const String &json, const char *const key,
                           double *const value)
    {
      if (key == nullptr || value == nullptr)
      {
        return false;
      }

      const String needle = String('"') + key + '"';
      int cursor = json.indexOf(needle);
      if (cursor < 0)
      {
        return false;
      }
      cursor = json.indexOf(':', cursor + needle.length());
      if (cursor < 0)
      {
        return false;
      }

      const char *text = json.c_str() + cursor + 1;
      while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n')
      {
        ++text;
      }

      char *end = nullptr;
      const double parsed = std::strtod(text, &end);
      if (end == text)
      {
        return false;
      }
      *value = parsed;
      return true;
    }

    bool ExtractJsonBool(const String &json, const char *const key,
                         bool *const value)
    {
      if (key == nullptr || value == nullptr)
      {
        return false;
      }

      const String needle = String('"') + key + '"';
      int cursor = json.indexOf(needle);
      if (cursor < 0)
      {
        return false;
      }
      cursor = json.indexOf(':', cursor + needle.length());
      if (cursor < 0)
      {
        return false;
      }

      const char *text = json.c_str() + cursor + 1;
      while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n')
      {
        ++text;
      }
      if (std::strncmp(text, "true", 4) == 0)
      {
        *value = true;
        return true;
      }
      if (std::strncmp(text, "false", 5) == 0)
      {
        *value = false;
        return true;
      }
      return false;
    }

    std::uint8_t NormalizeThresholdPercent(const double threshold)
    {
      double percent = threshold <= 1.0 ? threshold * 100.0 : threshold;
      if (percent < 0.0)
      {
        percent = 0.0;
      }
      if (percent > 100.0)
      {
        percent = 100.0;
      }
      return static_cast<std::uint8_t>(percent + 0.5);
    }

    bool ApplyLocalConfigJson(const String &json)
    {
      double plastic = 0.0;
      double paper = 0.0;
      double organic = 0.0;
      bool maintenance = false;
      if (!ExtractJsonNumber(json, "plastic", &plastic) ||
          !ExtractJsonNumber(json, "paper", &paper) ||
          !ExtractJsonNumber(json, "organic", &organic))
      {
        return false;
      }

      ExtractJsonBool(json, "maintenanceMode", &maintenance);
      g_dashboard_config.plastic_threshold =
          NormalizeThresholdPercent(plastic);
      g_dashboard_config.paper_threshold = NormalizeThresholdPercent(paper);
      g_dashboard_config.organic_threshold =
          NormalizeThresholdPercent(organic);
      g_dashboard_config.maintenance_mode = maintenance;
      g_dashboard_config.loaded = true;
      return true;
    }

    bool PullLocalDashboardConfig()
    {
      if (WiFi.status() != WL_CONNECTED)
      {
        return false;
      }

      HttpEndpoint endpoint{};
      if (!ParseHttpEndpoint(network_config::kServerUrl, &endpoint))
      {
        Serial.println("Config URL base must be plain HTTP");
        return false;
      }

      std::snprintf(endpoint.path, sizeof(endpoint.path),
                    "/api/devices/%s/config", network_config::kDeviceId);

      WiFiClient client;
      client.setTimeout(network_config::kHttpResponseTimeoutMs);
      if (!client.connect(endpoint.host, endpoint.port,
                          network_config::kHttpConnectTimeoutMs))
      {
        Serial.printf("Local config connect failed: %s:%u\n", endpoint.host,
                      static_cast<unsigned>(endpoint.port));
        return false;
      }

      client.printf("GET %s HTTP/1.1\r\n", endpoint.path);
      if (endpoint.port == 80)
      {
        client.printf("Host: %s\r\n", endpoint.host);
      }
      else
      {
        client.printf("Host: %s:%u\r\n", endpoint.host,
                      static_cast<unsigned>(endpoint.port));
      }
      client.println("Connection: close");
      client.println("Cache-Control: no-cache");
      client.println("Pragma: no-cache");
      client.println();

      String body;
      const int response_code = ReadHttpResponseBody(&client, &body, 1024);
      client.stop();
      if (response_code < 200 || response_code >= 300)
      {
        Serial.printf("Local config pull failed: HTTP %d\n", response_code);
        return false;
      }
      if (!ApplyLocalConfigJson(body))
      {
        Serial.println("Local config response could not be parsed");
        return false;
      }

      Serial.printf("Local config applied: plastic=%u paper=%u organic=%u "
                    "maintenance=%u\n",
                    static_cast<unsigned>(
                        g_dashboard_config.plastic_threshold),
                    static_cast<unsigned>(g_dashboard_config.paper_threshold),
                    static_cast<unsigned>(
                        g_dashboard_config.organic_threshold),
                    g_dashboard_config.maintenance_mode ? 1U : 0U);
      // G is valid in every Nano state. During an upload transaction it must
      // be sent before D so the Nano re-evaluates its LEDs with the exact fill
      // values that were just persisted by the server.
      SendNanoConfig();
      return true;
    }

    ServerSyncResult UploadRecognition(
        const NanoResult nano_result,
        const RecognitionTelemetry &telemetry,
        const CompartmentFillLevels &fill_levels)
    {
      if (telemetry.jpeg_data == nullptr || telemetry.jpeg_length == 0U)
      {
        Serial.println("No JPEG available; telemetry upload skipped");
        return ServerSyncResult::kNoJpeg;
      }
      if (WiFi.status() != WL_CONNECTED)
      {
        Serial.println("No Wi-Fi; telemetry upload skipped");
        return ServerSyncResult::kWifiUnavailable;
      }

      HttpEndpoint endpoint{};
      if (!ParseHttpEndpoint(network_config::kServerUrl, &endpoint))
      {
        Serial.println("Telemetry URL must be plain HTTP");
        return ServerSyncResult::kInvalidUrl;
      }

      WiFiClient client;
      client.setTimeout(network_config::kHttpResponseTimeoutMs);
      if (!client.connect(endpoint.host, endpoint.port,
                          network_config::kHttpConnectTimeoutMs))
      {
        const String local_ip = WiFi.localIP().toString();
        const String gateway_ip = WiFi.gatewayIP().toString();
        Serial.printf(
            "Unable to connect to telemetry server %s:%u "
            "(ESP IP=%s, gateway=%s, RSSI=%d dBm)\n",
            endpoint.host, static_cast<unsigned>(endpoint.port),
            local_ip.c_str(), gateway_ip.c_str(), WiFi.RSSI());
        Serial.println(
            "Check that server-tmp is running and kServerUrl uses the "
            "computer's current Wi-Fi IPv4 address");
        return ServerSyncResult::kConnectFailed;
      }

      client.printf("POST %s HTTP/1.1\r\n", endpoint.path);
      if (endpoint.port == 80)
      {
        client.printf("Host: %s\r\n", endpoint.host);
      }
      else
      {
        client.printf("Host: %s:%u\r\n", endpoint.host,
                      static_cast<unsigned>(endpoint.port));
      }
      client.println("Connection: close");
      client.println("Content-Type: image/jpeg");
      AddUnsignedHeader(&client, "Content-Length",
                        static_cast<unsigned long>(telemetry.jpeg_length));
      client.printf("X-Device-Id: %s\r\n", network_config::kDeviceId);
      client.printf("X-Device-Token: %s\r\n", network_config::kDeviceToken);
      client.printf("X-Model-Sha256: %s\r\n", g_model_sha256);
      client.printf("X-Firmware-Version: %s\r\n",
                    network_config::kFirmwareVersion);
      client.printf("X-Ai-Model-Version: %s\r\n",
                    network_config::kAiModelVersion);
      AddUnsignedHeader(&client, "X-Result-Code",
                        static_cast<unsigned long>(nano_result));
      AddUnsignedHeader(&client, "X-Image-Width", telemetry.frame_width);
      AddUnsignedHeader(&client, "X-Image-Height", telemetry.frame_height);
      AddUnsignedHeader(&client, "X-Fill-Plastic", fill_levels.plastic);
      AddUnsignedHeader(&client, "X-Fill-Paper", fill_levels.paper);
      AddUnsignedHeader(&client, "X-Fill-Organic", fill_levels.organic);

      if (telemetry.has_inference_result)
      {
        const ClassificationResult &result = telemetry.classification;
        AddFloatHeader(&client, "X-Confidence", result.confidence);
        AddFloatHeader(&client, "X-Paper-Probability", result.probabilities[0]);
        AddFloatHeader(&client, "X-Plastic-Probability", result.probabilities[1]);
        AddFloatHeader(&client, "X-Organic-Probability", result.probabilities[2]);
        AddInt64Header(&client, "X-Inference-Us", result.inference_time_us);
      }
      else
      {
        AddFloatHeader(&client, "X-Confidence", 0.0F);
        AddFloatHeader(&client, "X-Paper-Probability", 0.0F);
        AddFloatHeader(&client, "X-Plastic-Probability", 0.0F);
        AddFloatHeader(&client, "X-Organic-Probability", 0.0F);
        AddInt64Header(&client, "X-Inference-Us", 0);
      }
      client.println();

      constexpr std::size_t kUploadChunkBytes = 1024U;
      std::size_t written = 0U;
      const std::uint32_t write_started_at = millis();
      while (written < telemetry.jpeg_length && client.connected() &&
             millis() - write_started_at <
                 network_config::kHttpResponseTimeoutMs)
      {
        const std::size_t remaining = telemetry.jpeg_length - written;
        const std::size_t chunk =
            remaining < kUploadChunkBytes ? remaining : kUploadChunkBytes;
        const std::size_t sent =
            client.write(telemetry.jpeg_data + written, chunk);
        if (sent == 0U)
        {
          delay(2);
          continue;
        }
        written += sent;
        delay(1);
      }
      if (written != telemetry.jpeg_length)
      {
        client.stop();
        Serial.printf("Telemetry upload failed: wrote %u/%u JPEG bytes\n",
                      static_cast<unsigned>(written),
                      static_cast<unsigned>(telemetry.jpeg_length));
        return ServerSyncResult::kWriteFailed;
      }

      char response_body[181]{};
      const int response_code =
          ReadHttpResponseCode(&client, response_body, sizeof(response_body));
      client.stop();

      if (response_code >= 200 && response_code < 300)
      {
        Serial.printf("Telemetry uploaded: HTTP %d, %u JPEG bytes\n",
                      response_code,
                      static_cast<unsigned>(telemetry.jpeg_length));
        return ServerSyncResult::kSuccess;
      }

      Serial.printf("Telemetry upload failed: HTTP %d (%s)\n", response_code,
                    response_body);
      return ServerSyncResult::kHttpFailed;
    }

    bool InitializeAiPipeline()
    {
      Status status = g_classifier.Initialize();
      if (status != Status::kOk)
      {
        Serial.printf("Classifier initialization failed: %s\n",
                      StatusName(status));
        return false;
      }
      Serial.printf("Model self-test passed: %d bytes, SHA-256=%s\n",
                    g_model_len, g_model_sha256);

      TfLiteTensor *const input = g_classifier.input_tensor();
      if (input == nullptr)
      {
        Serial.println("Classifier has no input tensor");
        return false;
      }

      status =
          g_preprocessor.Configure(input->params.scale, input->params.zero_point);
      if (status != Status::kOk)
      {
        Serial.printf("Preprocessor initialization failed: %s\n",
                      StatusName(status));
        return false;
      }

      status = g_camera.Initialize();
      if (status != Status::kOk)
      {
        Serial.printf("Camera initialization failed: %s\n", StatusName(status));
        return false;
      }

      WarmUpCamera();
      return true;
    }

  } // namespace

  void SetupFirmware()
  {
    Serial.begin(kDebugBaud);
    Serial.setDebugOutput(true);
    delay(800);

    g_nano_serial.setRxBufferSize(kNanoRxBufferBytes);
    g_nano_serial.begin(kNanoBaud, SERIAL_8N1, kNanoRxPin, kNanoTxPin);

    Serial.println();
    Serial.println("AIoT Smart Trash Bin - ESP32-CAM AI Thinker");
    Serial.println("UART2: 9600 8N1, RX=GPIO13, TX=GPIO14");
    LogMemory("boot");

    // Chi bat dau Wi-Fi; khong cho ket noi truoc khi khoi dong AI/UART.
    const bool wifi_connected = InitializeWifi();
    if (!wifi_connected)
    {
      Serial.println("Wi-Fi is connecting in background; local AI/UART continue");
    }
    LogMemory("network ready");

    g_ready = InitializeAiPipeline();
    if (!g_ready)
    {
      Serial.println("AI pipeline unavailable; valid UART requests return 0");
    }
    else
    {
      LogMemory("AI ready");
      Serial.printf("Model arena used: %u bytes\n",
                    static_cast<unsigned>(g_classifier.arena_used_bytes()));
    }

    const bool wifi_confirmed = ConfirmInitialWifiConnectivity();
    if (wifi_confirmed)
    {
      PullLocalDashboardConfig();
    }

    MaintainCameraWebServices();
    Serial.printf("Local sync: ESP JPEG -> http://%s:%u%s\n",
                  network_config::kLocalServerHost,
                  static_cast<unsigned>(network_config::kLocalServerPort),
                  network_config::kLocalServerUploadPath);
    Serial.println("Remote sync disabled; only the local Python server is used");
    Serial.printf(
        "ESP initialized; waiting for Nano H 1 probe; initial Wi-Fi=%s; "
        "commands: T 1, "
        "F <plastic> <paper> <organic>, WIFI_RESET\n",
        wifi_confirmed ? "connected" : "offline");
  }

  void LoopFirmware()
  {
    MaintainWifiConnection();
    MaintainCameraWebServices();

    bool command_from_nano = false;
    bool command_from_monitor = false;

    // Nhận lệnh thật từ Arduino Nano qua UART2.
    command_from_nano = ReadNanoCaptureCommand();

    // UART0 keeps test command 1, accepts T 1, and keeps WIFI_RESET.
    command_from_monitor = ReadMonitorCaptureCommand();

    // Chưa nhận lệnh từ cả Nano lẫn Serial Monitor.
    if (!command_from_nano && !command_from_monitor)
    {
      delay(2);
      return;
    }

    if (command_from_nano)
    {
      Serial.println("Capture command received from Nano");
    }
    else
    {
      Serial.println("Test command received from Serial Monitor");
    }
    // Discard any standalone/stale F received before this accepted T 1. Only
    // the F sent by Nano after C belongs to this recognition event.
    g_fill_levels.received = false;

    RecognitionTelemetry telemetry;
    const NanoResult result = CaptureAndClassify(&telemetry);

    if (command_from_nano)
    {
      // Chỉ gửi kết quả 0-3 về Nano khi Nano là bên yêu cầu.
      SendNanoMessage("C", static_cast<std::uint8_t>(result));

      Serial.printf(
          "Result sent to Nano: %u\n",
          static_cast<unsigned>(result));
    }
    else
    {
      // Khi test bằng Monitor chỉ hiển thị kết quả trên máy.
      Serial.printf(
          "Test result: %u\n",
          static_cast<unsigned>(result));
    }

    // Keep the captured JPEG alive until the real Nano or Serial Monitor test
    // supplies all three fill levels for the same recognition event.
    const bool fill_levels_received = command_from_nano
                                          ? WaitForNanoFillLevels()
                                          : WaitForMonitorFillLevels();
    if (!fill_levels_received)
    {
      if (command_from_nano)
      {
        FinishNanoTransaction(ServerSyncResult::kFillTimeout);
      }
      return;
    }

    ServerSyncResult sync_result = ServerSyncResult::kWifiUnavailable;
    if (!EnsureWifiConnectedForUpload())
    {
      Serial.println("Local server sync skipped: Wi-Fi reconnect timed out");
    }
    else
    {
      sync_result = UploadRecognition(result, telemetry, g_fill_levels);
    }
    if (WiFi.status() == WL_CONNECTED)
    {
      // Required order for a real Nano transaction:
      // POST telemetry -> GET dashboard config -> G thresholds -> D result.
      // The config fetch remains useful after a failed POST as long as the
      // server is reachable, so the Nano can still receive the latest policy.
      PullLocalDashboardConfig();
    }
    if (command_from_nano)
    {
      FinishNanoTransaction(sync_result);
    }
  }
} // namespace aiot
