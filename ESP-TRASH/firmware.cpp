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
    constexpr std::size_t kNanoRxBufferBytes = 64;
    constexpr std::size_t kNanoCommandBufferBytes = 32;
    constexpr unsigned long kCaptureRetryDelayMs = 30;
    constexpr std::size_t kMonitorCommandBufferBytes = 24;

    enum class WifiState : std::uint8_t
    {
      kIdle,
      kConnectingStored,
      kConnected,
      kOffline,
    };

    // This is the wire protocol expected by the Nano. It intentionally differs
    // from the model label indices (paper=0, plastic=1, organic=2, other=3).
    enum class NanoResult : std::uint8_t
    {
      kNotRecognized = 0,
      kPlastic = 1,
      kPaper = 2,
      kOrganic = 3,
    };

    struct RecognitionTelemetry
    {
      std::uint8_t *jpeg_data = nullptr;
      std::size_t jpeg_length = 0;
      unsigned frame_width = 0;
      unsigned frame_height = 0;
      unsigned frame_length = 0;
      ClassificationResult classification{};
      bool has_classification = false;

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

    TflmClassifier g_classifier;
    ImagePreprocessor g_preprocessor;
    CameraAdapter g_camera;
    bool g_ready = false;
    bool g_camera_web_ready = false;
    bool g_mdns_ready = false;
    volatile WifiState g_wifi_state = WifiState::kIdle;
    std::uint32_t g_last_camera_service_attempt_ms = 0;
    CompartmentFillLevels g_fill_levels;
    CompartmentAlertState g_alert_state;

    constexpr std::uint32_t kCameraServiceRetryIntervalMs = 5000;

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
      if (ParseNanoTrigger(command))
      {
        return true;
      }

      CompartmentFillLevels levels;
      if (ParseNanoFillLevels(command, &levels))
      {
        g_fill_levels = levels;
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
      case model_contract::WasteClass::kOther:
        return NanoResult::kNotRecognized;
      }
      return NanoResult::kNotRecognized;
    }

    const char *NanoResultWasteType(const NanoResult result)
    {
      switch (result)
      {
      case NanoResult::kPlastic:
        return "plastic";
      case NanoResult::kPaper:
        return "paper";
      case NanoResult::kOrganic:
        return "organic";
      case NanoResult::kNotRecognized:
        return nullptr;
      }
      return nullptr;
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

    bool WaitForWifi(const std::uint32_t timeout_ms)
    {
      const std::uint32_t started_at = millis();
      while (WiFi.status() != WL_CONNECTED &&
             millis() - started_at < timeout_ms)
      {
        delay(250);
        Serial.print('.');
      }
      return WiFi.status() == WL_CONNECTED;
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
      g_wifi_state = state;
      Serial.printf("Wi-Fi state: %s\n", WifiStateName(state));
    }

    bool ConnectStoredWifi(const std::uint32_t timeout_ms)
    {
      if (WiFi.status() == WL_CONNECTED)
      {
        SetWifiState(WifiState::kConnected);
        return true;
      }

      SetWifiState(WifiState::kConnectingStored);
      Serial.print("Connecting with stored Wi-Fi credentials");
      WiFi.begin();
      const bool connected = WaitForWifi(timeout_ms);
      Serial.println();

      if (!connected)
      {
        SetWifiState(WifiState::kOffline);
        Serial.println("Stored Wi-Fi connection timed out");
        return false;
      }

      SetWifiState(WifiState::kConnected);
      Serial.printf("Wi-Fi connected: IP=%s RSSI=%d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
    }

    bool HasConfiguredWifi()
    {
      return WIFI_SSID[0] != '\0';
    }

    bool ConnectConfiguredWifi(const std::uint32_t timeout_ms)
    {
      if (!HasConfiguredWifi())
      {
        return false;
      }

      SetWifiState(WifiState::kConnectingStored);
      Serial.print("Connecting with secrets.h Wi-Fi credentials");
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      const bool connected = WaitForWifi(timeout_ms);
      Serial.println();

      if (!connected)
      {
        SetWifiState(WifiState::kOffline);
        Serial.println("secrets.h Wi-Fi connection timed out");
        return false;
      }

      SetWifiState(WifiState::kConnected);
      Serial.printf("Wi-Fi connected: IP=%s RSSI=%d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
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

      bool connected = ConnectStoredWifi(network_config::kInitialWifiTimeoutMs);
      if (!connected)
      {
        connected = ConnectConfiguredWifi(network_config::kInitialWifiTimeoutMs);
      }
      return connected;
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

    bool EnsureWifiConnected()
    {
      if (WiFi.status() == WL_CONNECTED)
      {
        return true;
      }

      Serial.println("Wi-Fi disconnected; reconnecting");
      WiFi.reconnect();
      if (WaitForWifi(network_config::kReconnectTimeoutMs))
      {
        Serial.printf("Wi-Fi reconnected: IP=%s\n",
                      WiFi.localIP().toString().c_str());
        return true;
      }

      Serial.println();
      return ConnectStoredWifi(network_config::kReconnectTimeoutMs);
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
          "Enter F <plastic> <paper> <organic> to continue cloud sync");
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
      Serial.println("Monitor fill-level timeout; cloud sync cancelled");
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

      {
        CameraFrameLease frame = g_camera.Capture(&status);
        if (!frame || status != Status::kOk)
        {
          // One short retry handles an occasional transient frame-buffer miss.
          delay(kCaptureRetryDelayMs);
          frame = g_camera.Capture(&status);
        }
        if (!frame || status != Status::kOk)
        {
          Serial.printf("Capture failed: %s\n", StatusName(status));
          return NanoResult::kNotRecognized;
        }

        telemetry->frame_width = frame.get()->width;
        telemetry->frame_height = frame.get()->height;
        telemetry->frame_length = frame.get()->len;

        ImageView view{};
        status = CameraAdapter::MakeImageView(*frame.get(), &view);
        if (status == Status::kOk)
        {
          status = g_preprocessor.Run(view, input->data.int8, input->bytes);
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

      status = g_classifier.Classify(&telemetry->classification);
      if (status != Status::kOk)
      {
        Serial.printf("Inference failed: %s\n", StatusName(status));
        return NanoResult::kNotRecognized;
      }
      telemetry->has_classification = true;

      const NanoResult nano_result =
          ToNanoResult(telemetry->classification.predicted);
      const ClassificationResult &result = telemetry->classification;
      Serial.printf(
          "Frame=%ux%u/%uB JPEG=%uB class=%s confidence=%.4f "
          "p=[paper %.4f, plastic %.4f, organic %.4f, other %.4f] inference=%" PRId64
          " us -> Nano=%u\n",
          telemetry->frame_width, telemetry->frame_height,
          telemetry->frame_length,
          static_cast<unsigned>(telemetry->jpeg_length),
          ClassName(result.predicted), static_cast<double>(result.confidence),
          static_cast<double>(result.probabilities[0]),
          static_cast<double>(result.probabilities[1]),
          static_cast<double>(result.probabilities[2]),
          static_cast<double>(result.probabilities[3]), result.inference_time_us,
          static_cast<unsigned>(nano_result));

      return nano_result;
    }

#if 0
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

    int ReadHttpResponseCode(WiFiClient *const client, char *const body_preview,
                             const std::size_t body_preview_size)
    {
      if (client == nullptr)
      {
        return -1;
      }

      String status_line = client->readStringUntil('\n');
      status_line.trim();
      int response_code = -1;
      if (status_line.startsWith("HTTP/"))
      {
        const int first_space = status_line.indexOf(' ');
        if (first_space >= 0)
        {
          response_code = status_line.substring(first_space + 1).toInt();
        }
      }

      while (client->connected() || client->available() > 0)
      {
        const String header_line = client->readStringUntil('\n');
        if (header_line == "\r" || header_line.length() == 0)
        {
          break;
        }
      }

      if (body_preview != nullptr && body_preview_size > 0U)
      {
        std::size_t length = 0;
        const std::uint32_t started_at = millis();
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

    bool UploadRecognition(const NanoResult nano_result,
                           const RecognitionTelemetry &telemetry)
    {
      if (telemetry.jpeg_data == nullptr || telemetry.jpeg_length == 0U)
      {
        Serial.println("No JPEG available; telemetry upload skipped");
        return false;
      }
      if (!EnsureWifiConnected())
      {
        Serial.println("No Wi-Fi; telemetry upload skipped");
        return false;
      }

      HttpEndpoint endpoint{};
      if (!ParseHttpEndpoint(network_config::kServerUrl, &endpoint))
      {
        Serial.println("Telemetry URL must be plain HTTP");
        return false;
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
        return false;
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
      AddUnsignedHeader(&client, "X-Result-Code",
                        static_cast<unsigned long>(nano_result));
      AddUnsignedHeader(&client, "X-Image-Width", telemetry.frame_width);
      AddUnsignedHeader(&client, "X-Image-Height", telemetry.frame_height);

      if (telemetry.has_classification)
      {
        const ClassificationResult &result = telemetry.classification;
        AddFloatHeader(&client, "X-Confidence", result.confidence);
        AddFloatHeader(&client, "X-Paper-Probability", result.probabilities[0]);
        AddFloatHeader(&client, "X-Plastic-Probability", result.probabilities[1]);
        AddFloatHeader(&client, "X-Organic-Probability", result.probabilities[2]);
        AddFloatHeader(&client, "X-Other-Probability", result.probabilities[3]);
        AddInt64Header(&client, "X-Inference-Us", result.inference_time_us);
      }
      else
      {
        AddFloatHeader(&client, "X-Confidence", 0.0F);
        AddFloatHeader(&client, "X-Paper-Probability", 0.0F);
        AddFloatHeader(&client, "X-Plastic-Probability", 0.0F);
        AddFloatHeader(&client, "X-Organic-Probability", 0.0F);
        AddFloatHeader(&client, "X-Other-Probability", 0.0F);
        AddInt64Header(&client, "X-Inference-Us", 0);
      }
      client.println();

      const std::size_t written =
          client.write(telemetry.jpeg_data, telemetry.jpeg_length);
      if (written != telemetry.jpeg_length)
      {
        client.stop();
        Serial.println("Telemetry upload failed: incomplete JPEG write");
        return false;
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
        return true;
      }

      Serial.printf("Telemetry upload failed: HTTP %d (%s)\n", response_code,
                    response_body);
      return false;
    }
#endif

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

    // Connect before allocating camera/TFLM resources so NTP is ready early.
    const bool wifi_connected = InitializeWifi();
    if (!wifi_connected)
    {
      Serial.println("Wi-Fi unavailable; local AI and UART will still start");
    }
    else
    {
      InitializeCloudClock();
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

    MaintainCameraWebServices();
    Serial.println(
        "Waiting for Nano T 1 or Serial Monitor 1 T 1 WIFI_RESET");
  }

  void LoopFirmware()
  {
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

    RecognitionTelemetry telemetry;
    const NanoResult result = CaptureAndClassify(&telemetry);
    g_fill_levels.received = false;

    if (command_from_nano)
    {
      // Chỉ gửi kết quả 0-3 về Nano khi Nano là bên yêu cầu.
      g_nano_serial.print("C ");
      g_nano_serial.println(static_cast<std::uint8_t>(result));

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
      return;
    }

    if (!EnsureWifiConnected())
    {
      Serial.println("Cloud sync skipped: Wi-Fi unavailable");
      return;
    }

    CloudRecognition cloud_recognition{};
    cloud_recognition.jpeg_data = telemetry.jpeg_data;
    cloud_recognition.jpeg_length = telemetry.jpeg_length;
    cloud_recognition.waste_type = NanoResultWasteType(result);
    cloud_recognition.confidence = telemetry.has_classification
                                       ? telemetry.classification.confidence
                                       : 0.0F;
    cloud_recognition.has_classification = telemetry.has_classification;
    const String image_url = UploadRecognitionImage(cloud_recognition);
    SyncRecognitionToCloud(cloud_recognition, g_fill_levels, image_url);
    SendFullAlertsIfNeeded(g_fill_levels, &g_alert_state, image_url.c_str());
  }
} // namespace aiot
