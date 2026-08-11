#include "cloud_sync.h"

#include <Arduino.h>
#include <WiFi.h>

#include <cstdint>
#include <cstring>
#include <ctime>

#include "esp_crt_bundle.h"
#include "esp_http_client.h"

#include "network_config.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef CLOUDINARY_CLOUD_NAME
#define CLOUDINARY_CLOUD_NAME ""
#endif

#ifndef CLOUDINARY_UPLOAD_PRESET
#define CLOUDINARY_UPLOAD_PRESET ""
#endif

#ifndef FIREBASE_DEVICE_ID
#define FIREBASE_DEVICE_ID ""
#endif

#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL ""
#endif

#ifndef DEVICE_PROVISION_SECRET
#define DEVICE_PROVISION_SECRET ""
#endif

namespace aiot
{
  namespace
  {
    struct HttpResponse
    {
      int status_code = -1;
      String body;
    };

    struct EventPayload
    {
      const char *event_type = nullptr;
      const char *waste_type = nullptr;
      const char *target_compartment = nullptr;
      bool has_ai_confidence = false;
      float ai_confidence = 0.0F;
      const CompartmentFillLevels *fill_levels = nullptr;
      bool has_alert_threshold = false;
      std::uint8_t alert_threshold = 0;
      const char *device_timestamp = nullptr;
      const char *image_url = nullptr;
    };

    String g_device_token;
    std::uint32_t g_device_token_valid_until_ms = 0;

    bool IsHttpSuccess(const int status_code)
    {
      return status_code >= 200 && status_code < 300;
    }

    bool HasCloudinaryConfiguration()
    {
      return CLOUDINARY_CLOUD_NAME[0] != '\0' &&
             CLOUDINARY_UPLOAD_PRESET[0] != '\0';
    }

    bool HasBackendConfiguration()
    {
      return BACKEND_BASE_URL[0] != '\0' &&
             DEVICE_PROVISION_SECRET[0] != '\0';
    }

    const char *DeviceId()
    {
      return FIREBASE_DEVICE_ID[0] != '\0' ? FIREBASE_DEVICE_ID
                                            : network_config::kDeviceId;
    }

    String BackendBaseUrl()
    {
      String url = BACKEND_BASE_URL;
      url.trim();
      if (!url.startsWith("http://") && !url.startsWith("https://"))
      {
        url = String("http://") + url;
      }
      while (url.endsWith("/"))
      {
        url.remove(url.length() - 1U);
      }
      return url;
    }

    String JsonEscape(const char *const value)
    {
      String escaped;
      if (value == nullptr)
      {
        return escaped;
      }

      escaped.reserve(std::strlen(value) + 8U);
      for (const char *cursor = value; *cursor != '\0'; ++cursor)
      {
        switch (*cursor)
        {
        case '\\':
          escaped += F("\\\\");
          break;
        case '"':
          escaped += F("\\\"");
          break;
        case '\n':
          escaped += F("\\n");
          break;
        case '\r':
          escaped += F("\\r");
          break;
        case '\t':
          escaped += F("\\t");
          break;
        default:
          escaped += *cursor;
          break;
        }
      }
      return escaped;
    }

    void AppendNullableJsonString(String *const json, const char *const value)
    {
      if (value == nullptr || value[0] == '\0')
      {
        *json += F("null");
        return;
      }
      *json += '"';
      *json += JsonEscape(value);
      *json += '"';
    }

    bool ExtractJsonString(const String &json, const char *const key,
                           String *const value)
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
      cursor = json.indexOf('"', cursor + 1);
      if (cursor < 0)
      {
        return false;
      }

      String decoded;
      for (++cursor; cursor < static_cast<int>(json.length()); ++cursor)
      {
        const char current = json[cursor];
        if (current == '"')
        {
          *value = decoded;
          return true;
        }
        if (current != '\\')
        {
          decoded += current;
          continue;
        }

        ++cursor;
        if (cursor >= static_cast<int>(json.length()))
        {
          return false;
        }
        const char escaped = json[cursor];
        switch (escaped)
        {
        case '"':
        case '\\':
        case '/':
          decoded += escaped;
          break;
        case 'n':
          decoded += '\n';
          break;
        case 'r':
          decoded += '\r';
          break;
        case 't':
          decoded += '\t';
          break;
        default:
          return false;
        }
      }
      return false;
    }

    bool WriteAll(esp_http_client_handle_t client, const char *data,
                  const std::size_t length)
    {
      std::size_t written = 0;
      while (written < length)
      {
        const int chunk = esp_http_client_write(
            client, data + written, static_cast<int>(length - written));
        if (chunk <= 0)
        {
          return false;
        }
        written += static_cast<std::size_t>(chunk);
      }
      return true;
    }

    HttpResponse FinishHttpRequest(esp_http_client_handle_t client)
    {
      HttpResponse response;
      const std::int64_t content_length = esp_http_client_fetch_headers(client);
      response.status_code = esp_http_client_get_status_code(client);
      if (response.status_code <= 0)
      {
        esp_http_client_close(client);
        return response;
      }

      if (content_length > 0 && content_length < 8192)
      {
        response.body.reserve(static_cast<unsigned>(content_length));
      }

      char buffer[512];
      while (true)
      {
        const int read = esp_http_client_read(client, buffer, sizeof(buffer));
        if (read > 0)
        {
          if (response.body.length() + static_cast<unsigned>(read) <= 8192U)
          {
            response.body.concat(buffer, static_cast<unsigned>(read));
          }
          continue;
        }
        if (read == -ESP_ERR_HTTP_EAGAIN)
        {
          delay(1);
          continue;
        }
        break;
      }
      esp_http_client_close(client);
      return response;
    }

    esp_http_client_handle_t CreateHttpClient(
        const String &url, const esp_http_client_method_t method)
    {
      esp_http_client_config_t config{};
      config.url = url.c_str();
      config.method = method;
      config.timeout_ms = network_config::kCloudHttpTimeoutMs;
      config.user_agent = "AIoT-ESP32-CAM/1.0";
      config.buffer_size = network_config::kCloudHttpReceiveBufferBytes;
      config.buffer_size_tx = network_config::kCloudHttpTransmitBufferBytes;
      config.crt_bundle_attach = esp_crt_bundle_attach;
      return esp_http_client_init(&config);
    }

    HttpResponse SendJsonRequest(const String &url,
                                 const esp_http_client_method_t method,
                                 const String &json,
                                 const char *const authorization,
                                 const char *const extra_header_name = nullptr,
                                 const char *const extra_header_value = nullptr)
    {
      HttpResponse response;
      esp_http_client_handle_t client = CreateHttpClient(url, method);
      if (client == nullptr)
      {
        return response;
      }

      esp_http_client_set_header(client, "Content-Type", "application/json");
      if (authorization != nullptr && authorization[0] != '\0')
      {
        esp_http_client_set_header(client, "Authorization", authorization);
      }
      if (extra_header_name != nullptr && extra_header_value != nullptr)
      {
        esp_http_client_set_header(client, extra_header_name,
                                   extra_header_value);
      }

      const esp_err_t opened =
          esp_http_client_open(client, static_cast<int>(json.length()));
      if (opened != ESP_OK)
      {
        Serial.printf("HTTP connection failed: url=%s error=%s\n",
                      url.c_str(), esp_err_to_name(opened));
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return response;
      }
      if (!WriteAll(client, json.c_str(), json.length()))
      {
        Serial.println("HTTP request body write failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return response;
      }

      response = FinishHttpRequest(client);
      esp_http_client_cleanup(client);
      return response;
    }

    bool DeviceTokenIsFresh()
    {
      if (g_device_token.isEmpty())
      {
        return false;
      }
      return static_cast<std::int32_t>(g_device_token_valid_until_ms -
                                       millis()) > 0;
    }

    bool AcquireDeviceToken()
    {
      if (!HasBackendConfiguration())
      {
        Serial.println(
            "Backend is not configured in secrets.h; sync skipped");
        return false;
      }

      String url = BackendBaseUrl();
      url += "/api/devices/";
      url += DeviceId();
      url += "/auth-token";
      Serial.printf("Backend auth request: %s\n", url.c_str());
      const HttpResponse response = SendJsonRequest(
          url, HTTP_METHOD_POST, String(), nullptr, "X-Provision-Secret",
          DEVICE_PROVISION_SECRET);

      String token;
      if (!IsHttpSuccess(response.status_code) ||
          !ExtractJsonString(response.body, "token", &token))
      {
        Serial.printf("Backend device authentication failed: HTTP %d\n",
                      response.status_code);
        if (!response.body.isEmpty())
        {
          String preview = response.body.substring(0, 300);
          preview.replace('\n', ' ');
          preview.replace('\r', ' ');
          Serial.printf("Backend auth error: %s\n", preview.c_str());
        }
        return false;
      }

      g_device_token = token;
      g_device_token_valid_until_ms =
          millis() + network_config::kBackendTokenRefreshMs;
      Serial.println("Backend device authentication ready");
      return true;
    }

    bool EnsureDeviceToken()
    {
      return DeviceTokenIsFresh() || AcquireDeviceToken();
    }

    bool GetUtcTimestamp(char *const output, const std::size_t output_size)
    {
      if (output == nullptr || output_size < 21U)
      {
        return false;
      }

      const std::time_t now = std::time(nullptr);
      if (now < network_config::kMinimumValidEpoch)
      {
        return false;
      }
      std::tm utc{};
      gmtime_r(&now, &utc);
      return std::strftime(output, output_size, "%Y-%m-%dT%H:%M:%SZ", &utc) >
             0U;
    }

    String UploadToCloudinaryImpl(const CloudRecognition &recognition)
    {
      String image_url;
      if (!HasCloudinaryConfiguration())
      {
        Serial.println(
            "Cloudinary is not configured in secrets.h; image upload skipped");
        return image_url;
      }
      if (recognition.jpeg_data == nullptr || recognition.jpeg_length == 0U)
      {
        Serial.println("Cloudinary upload skipped: JPEG is empty");
        return image_url;
      }

      constexpr char kBoundary[] = "----AIoTTrashBin7MA4YWxk";
      String prefix = "--";
      prefix += kBoundary;
      prefix +=
          "\r\nContent-Disposition: form-data; name=\"upload_preset\"\r\n\r\n";
      prefix += CLOUDINARY_UPLOAD_PRESET;
      prefix += "\r\n--";
      prefix += kBoundary;
      prefix +=
          "\r\nContent-Disposition: form-data; name=\"file\"; "
          "filename=\"capture.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
      String suffix = "\r\n--";
      suffix += kBoundary;
      suffix += "--\r\n";

      String url = "https://api.cloudinary.com/v1_1/";
      url += CLOUDINARY_CLOUD_NAME;
      url += "/image/upload";
      esp_http_client_handle_t client =
          CreateHttpClient(url, HTTP_METHOD_POST);
      if (client == nullptr)
      {
        return image_url;
      }

      String content_type = "multipart/form-data; boundary=";
      content_type += kBoundary;
      esp_http_client_set_header(client, "Content-Type", content_type.c_str());
      const std::size_t content_length =
          prefix.length() + recognition.jpeg_length + suffix.length();
      const esp_err_t opened =
          esp_http_client_open(client, static_cast<int>(content_length));
      const bool request_written = opened == ESP_OK &&
                                   WriteAll(client, prefix.c_str(),
                                            prefix.length()) &&
                                   WriteAll(client,
                                            reinterpret_cast<const char *>(
                                                recognition.jpeg_data),
                                            recognition.jpeg_length) &&
                                   WriteAll(client, suffix.c_str(),
                                            suffix.length());
      if (!request_written)
      {
        Serial.printf("Cloudinary request write failed: %s\n",
                      esp_err_to_name(opened));
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return image_url;
      }

      const HttpResponse response = FinishHttpRequest(client);
      esp_http_client_cleanup(client);
      if (!IsHttpSuccess(response.status_code) ||
          !ExtractJsonString(response.body, "secure_url", &image_url))
      {
        Serial.printf("Cloudinary upload failed: HTTP %d\n",
                      response.status_code);
        image_url = "";
        return image_url;
      }

      Serial.printf("Cloudinary upload complete: %u JPEG bytes\n",
                    static_cast<unsigned>(recognition.jpeg_length));
      Serial.printf("Cloudinary secure_url: %s\n", image_url.c_str());
      return image_url;
    }

    String BuildBackendEventJson(const EventPayload &payload)
    {
      String json;
      json.reserve(700);
      json += F("{\"eventType\":\"");
      json += JsonEscape(payload.event_type);
      json += F("\",\"wasteType\":");
      AppendNullableJsonString(&json, payload.waste_type);
      json += F(",\"targetCompartment\":");
      AppendNullableJsonString(&json, payload.target_compartment);
      json += F(",\"aiConfidence\":");
      if (payload.has_ai_confidence)
      {
        json += String(payload.ai_confidence, 6);
      }
      else
      {
        json += F("null");
      }
      json += F(",\"fillPercent\":{\"organic\":");
      json += static_cast<unsigned>(payload.fill_levels->organic);
      json += F(",\"paper\":");
      json += static_cast<unsigned>(payload.fill_levels->paper);
      json += F(",\"plastic\":");
      json += static_cast<unsigned>(payload.fill_levels->plastic);
      json += F("},\"alertThreshold\":");
      if (payload.has_alert_threshold)
      {
        json += static_cast<unsigned>(payload.alert_threshold);
      }
      else
      {
        json += F("null");
      }
      json += F(",\"deviceTimestamp\":\"");
      json += payload.device_timestamp;
      json += F("\",\"syncedLate\":false,\"firmwareVersion\":\"");
      json += JsonEscape(network_config::kFirmwareVersion);
      json += F("\",\"aiModelVersion\":\"");
      json += JsonEscape(network_config::kAiModelVersion);
      json += F("\",\"imageUrl\":");
      AppendNullableJsonString(&json, payload.image_url);
      json += '}';
      return json;
    }

    HttpResponse SendEventToBackend(const EventPayload &payload)
    {
      HttpResponse failure;
      if (!EnsureDeviceToken())
      {
        return failure;
      }

      String url = BackendBaseUrl();
      url += "/api/devices/";
      url += DeviceId();
      url += "/events";
      String authorization = "Bearer ";
      authorization += g_device_token;
      HttpResponse response = SendJsonRequest(
          url, HTTP_METHOD_POST, BuildBackendEventJson(payload),
          authorization.c_str());

      // A 401 is rejected by DeviceTokenFilter before the controller can write
      // an event, so refreshing the token and retrying exactly once cannot
      // duplicate a Firestore event. This commonly happens after a local
      // backend restart because its development JWT signing key changed.
      if (response.status_code == 401)
      {
        g_device_token = "";
        g_device_token_valid_until_ms = 0;
        Serial.println(
            "Backend rejected Device JWT; refreshing token and retrying once");
        if (AcquireDeviceToken())
        {
          authorization = "Bearer ";
          authorization += g_device_token;
          response = SendJsonRequest(
              url, HTTP_METHOD_POST, BuildBackendEventJson(payload),
              authorization.c_str());
        }
      }
      if (!IsHttpSuccess(response.status_code) && !response.body.isEmpty())
      {
        String preview = response.body.substring(0, 300);
        preview.replace('\n', ' ');
        preview.replace('\r', ' ');
        Serial.printf("Backend event error: HTTP %d: %s\n",
                      response.status_code, preview.c_str());
      }
      return response;
    }

    bool CheckAndUpdateAlert(const std::uint8_t fill_percent,
                             bool *const alerted)
    {
      const bool over = fill_percent >= network_config::kFullThresholdPercent;
      if (!over)
      {
        *alerted = false;
        return false;
      }
      if (*alerted)
      {
        return false;
      }
      *alerted = true;
      return true;
    }
  } // namespace

  bool InitializeCloudClock()
  {
    if (WiFi.status() != WL_CONNECTED)
    {
      return false;
    }

    configTime(0, 0, "pool.ntp.org", "time.google.com");
    const std::uint32_t started_at = millis();
    char timestamp[25]{};
    while (millis() - started_at < network_config::kClockSyncTimeoutMs)
    {
      if (GetUtcTimestamp(timestamp, sizeof(timestamp)))
      {
        Serial.printf("UTC synchronized: %s\n", timestamp);
        return true;
      }
      delay(200);
    }
    Serial.println("UTC synchronization timed out; cloud sync will retry later");
    return false;
  }

  bool PrepareCloudSync()
  {
    if (WiFi.status() != WL_CONNECTED)
    {
      Serial.println("Backend authentication skipped: Wi-Fi is offline");
      return false;
    }

    Serial.printf("Preparing backend sync: base=%s device=%s\n",
                  BackendBaseUrl().c_str(), DeviceId());
    return EnsureDeviceToken();
  }

  String UploadRecognitionImage(const CloudRecognition &recognition)
  {
    return UploadToCloudinaryImpl(recognition);
  }

  bool SyncRecognitionToCloud(const CloudRecognition &recognition,
                              const CompartmentFillLevels &fill_levels,
                              const String &image_url)
  {
    if (!fill_levels.received)
    {
      Serial.println("Backend sync skipped: Nano fill levels are missing");
      return false;
    }
    if (WiFi.status() != WL_CONNECTED)
    {
      Serial.println("Backend sync skipped: Wi-Fi is offline");
      return false;
    }

    char timestamp[25]{};
    if (!GetUtcTimestamp(timestamp, sizeof(timestamp)) &&
        (!InitializeCloudClock() ||
         !GetUtcTimestamp(timestamp, sizeof(timestamp))))
    {
      Serial.println("Backend sync skipped: UTC timestamp is unavailable");
      return false;
    }

    if (image_url.isEmpty())
    {
      Serial.println(
          "Cloudinary image unavailable; sending event without imageUrl");
    }

    const bool classified =
        recognition.has_classification && recognition.waste_type != nullptr;

    EventPayload payload{};
    payload.event_type = classified ? "CLASSIFY" : "ERROR";
    payload.waste_type = classified ? recognition.waste_type : nullptr;
    payload.target_compartment = payload.waste_type;
    payload.has_ai_confidence = classified;
    payload.ai_confidence = recognition.confidence;
    payload.fill_levels = &fill_levels;
    payload.has_alert_threshold = true;
    payload.alert_threshold = network_config::kFullThresholdPercent;
    payload.device_timestamp = timestamp;
    payload.image_url = image_url.c_str();

    const HttpResponse response = SendEventToBackend(payload);
    const bool succeeded = IsHttpSuccess(response.status_code);
    Serial.printf("Backend event: HTTP %d, type=%s\n", response.status_code,
                  payload.event_type);
    return succeeded;
  }

  int SendFullAlertsIfNeeded(const CompartmentFillLevels &fill_levels,
                             CompartmentAlertState *const alert_state,
                             const char *const image_url)
  {
    if (!fill_levels.received || alert_state == nullptr)
    {
      return 0;
    }
    if (WiFi.status() != WL_CONNECTED)
    {
      return 0;
    }

    char timestamp[25]{};
    if (!GetUtcTimestamp(timestamp, sizeof(timestamp)))
    {
      return 0;
    }

    struct Compartment
    {
      const char *name;
      std::uint8_t percent;
      bool *alerted;
    };
    Compartment compartments[3] = {
        {"organic", fill_levels.organic, &alert_state->organic_alerted},
        {"paper", fill_levels.paper, &alert_state->paper_alerted},
        {"plastic", fill_levels.plastic, &alert_state->plastic_alerted},
    };

    int sent_count = 0;
    for (const Compartment &compartment : compartments)
    {
      if (!CheckAndUpdateAlert(compartment.percent, compartment.alerted))
      {
        continue;
      }

      EventPayload payload{};
      payload.event_type = "FULL_ALERT";
      payload.target_compartment = compartment.name;
      payload.fill_levels = &fill_levels;
      payload.has_alert_threshold = true;
      payload.alert_threshold = network_config::kFullThresholdPercent;
      payload.device_timestamp = timestamp;
      payload.image_url = image_url;

      const HttpResponse response = SendEventToBackend(payload);
      Serial.printf("FULL_ALERT[%s]: HTTP %d\n", compartment.name,
                    response.status_code);
      if (IsHttpSuccess(response.status_code))
      {
        ++sent_count;
      }
      else
      {
        *compartment.alerted = false;
      }
    }
    return sent_count;
  }
} // namespace aiot
