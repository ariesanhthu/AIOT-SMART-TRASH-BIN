#include "cloud_sync.h"

#include <Arduino.h>
#include <WiFi.h>

#include <cstdint>
#include <cstdio>
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

#ifndef FIREBASE_PROJECT_ID
#define FIREBASE_PROJECT_ID ""
#endif

#ifndef FIREBASE_API_KEY
#define FIREBASE_API_KEY ""
#endif

#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL ""
#endif

#ifndef PROVISION_SECRET
#define PROVISION_SECRET ""
#endif

#ifndef FIREBASE_USER_EMAIL
#define FIREBASE_USER_EMAIL ""
#endif

#ifndef FIREBASE_USER_PASSWORD
#define FIREBASE_USER_PASSWORD ""
#endif

#ifndef FIREBASE_DEVICE_ID
#define FIREBASE_DEVICE_ID ""
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

    String g_firebase_id_token;
    std::uint32_t g_firebase_token_valid_until_ms = 0;

    bool IsHttpSuccess(const int status_code)
    {
      return status_code >= 200 && status_code < 300;
    }

    bool HasCloudinaryConfiguration()
    {
      return CLOUDINARY_CLOUD_NAME[0] != '\0' &&
             CLOUDINARY_UPLOAD_PRESET[0] != '\0';
    }

    bool HasFirebaseConfiguration()
    {
      const bool custom_token_flow =
          BACKEND_BASE_URL[0] != '\0' && PROVISION_SECRET[0] != '\0';
      const bool password_flow = FIREBASE_USER_EMAIL[0] != '\0' &&
                                 FIREBASE_USER_PASSWORD[0] != '\0';
      return FIREBASE_PROJECT_ID[0] != '\0' && FIREBASE_API_KEY[0] != '\0' &&
             (custom_token_flow || password_flow);
    }

    const char *DeviceId()
    {
      return FIREBASE_DEVICE_ID[0] != '\0' ? FIREBASE_DEVICE_ID
                                            : network_config::kDeviceId;
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

    esp_http_client_handle_t CreateHttpClient(const String &url,
                                               const esp_http_client_method_t method)
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
                                 const char *const provision_secret)
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
      if (provision_secret != nullptr && provision_secret[0] != '\0')
      {
        esp_http_client_set_header(client, "X-Provision-Secret",
                                   provision_secret);
      }

      const esp_err_t opened =
          esp_http_client_open(client, static_cast<int>(json.length()));
      if (opened != ESP_OK)
      {
        Serial.printf("HTTP connection failed before response: %s\n",
                      esp_err_to_name(opened));
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

    String JoinBackendUrl(const char *const path)
    {
      String url(BACKEND_BASE_URL);
      while (url.endsWith("/"))
      {
        url.remove(url.length() - 1U);
      }
      url += path;
      return url;
    }

    bool FirebaseTokenIsFresh()
    {
      if (g_firebase_id_token.isEmpty())
      {
        return false;
      }
      return static_cast<std::int32_t>(g_firebase_token_valid_until_ms -
                                       millis()) > 0;
    }

    bool AcquireFirebaseIdToken()
    {
      if (!HasFirebaseConfiguration())
      {
        Serial.println(
            "Firebase is not configured in secrets.h; database sync skipped");
        return false;
      }

      String exchange_url = "https://identitytoolkit.googleapis.com/v1/";
      String exchange_body;
      if (BACKEND_BASE_URL[0] != '\0' && PROVISION_SECRET[0] != '\0')
      {
        String token_path = "/api/devices/";
        token_path += DeviceId();
        token_path += "/auth-token";
        const HttpResponse custom_response = SendJsonRequest(
            JoinBackendUrl(token_path.c_str()), HTTP_METHOD_POST, "{}",
            nullptr, PROVISION_SECRET);
        String custom_token;
        if (!IsHttpSuccess(custom_response.status_code) ||
            !ExtractJsonString(custom_response.body, "customToken",
                               &custom_token))
        {
          Serial.printf("Firebase custom-token request failed: HTTP %d\n",
                        custom_response.status_code);
          return false;
        }

        exchange_url += "accounts:signInWithCustomToken?key=";
        exchange_body = F("{\"token\":\"");
        exchange_body += JsonEscape(custom_token.c_str());
        exchange_body += F("\",\"returnSecureToken\":true}");
      }
      else
      {
        exchange_url += "accounts:signInWithPassword?key=";
        exchange_body = F("{\"email\":\"");
        exchange_body += JsonEscape(FIREBASE_USER_EMAIL);
        exchange_body += F("\",\"password\":\"");
        exchange_body += JsonEscape(FIREBASE_USER_PASSWORD);
        exchange_body += F("\",\"returnSecureToken\":true}");
      }
      exchange_url += FIREBASE_API_KEY;

      const HttpResponse exchange_response = SendJsonRequest(
          exchange_url, HTTP_METHOD_POST, exchange_body, nullptr, nullptr);
      String id_token;
      if (!IsHttpSuccess(exchange_response.status_code) ||
          !ExtractJsonString(exchange_response.body, "idToken", &id_token))
      {
        Serial.printf("Firebase token exchange failed: HTTP %d\n",
                      exchange_response.status_code);
        return false;
      }

      g_firebase_id_token = id_token;
      g_firebase_token_valid_until_ms =
          millis() + network_config::kFirebaseTokenRefreshMs;
      Serial.println("Firebase device authentication ready");
      return true;
    }

    bool EnsureFirebaseIdToken()
    {
      return FirebaseTokenIsFresh() || AcquireFirebaseIdToken();
    }

    String FirestoreDocumentsBaseUrl()
    {
      String url = "https://firestore.googleapis.com/v1/projects/";
      url += FIREBASE_PROJECT_ID;
      url += "/databases/(default)/documents";
      return url;
    }

    String FirestoreDeviceDocumentName()
    {
      String name = "projects/";
      name += FIREBASE_PROJECT_ID;
      name += "/databases/(default)/documents/devices/";
      name += DeviceId();
      return name;
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

    String UploadToCloudinary(const CloudRecognition &recognition)
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

    const char *FillStatus(const std::uint8_t fill_percent)
    {
      return fill_percent >= network_config::kFullThresholdPercent ? "full"
                                                                   : "normal";
    }

    String BuildDeviceDocumentJson(const CloudRecognition &recognition,
                                   const CompartmentFillLevels &fill_levels,
                                   const char *const timestamp,
                                   const String &document_name)
    {
      const char *const class_name =
          recognition.waste_type != nullptr ? recognition.waste_type
                                            : "not_recognized";
      String json;
      json.reserve(1000);
      json += F("{\"name\":\"");
      json += document_name;
      json += F("\",\"fields\":{");
      json += F("\"last_seen_at\":{\"timestampValue\":\"");
      json += timestamp;
      json += F("\"},\"firmware_version\":{\"stringValue\":\"");
      json += network_config::kFirmwareVersion;
      json += F("\"},\"ai_model_version\":{\"stringValue\":\"");
      json += network_config::kAiModelVersion;
      json += F("\"},\"class_name\":{\"stringValue\":\"");
      json += class_name;
      json += F("\"},\"compartments\":{\"mapValue\":{\"fields\":{");

      json += F("\"organic\":{\"mapValue\":{\"fields\":{" 
                "\"fill_percent\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.organic);
      json += F("},\"status\":{\"stringValue\":\"");
      json += FillStatus(fill_levels.organic);
      json += F("\"}}}},");

      json += F("\"paper\":{\"mapValue\":{\"fields\":{" 
                "\"fill_percent\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.paper);
      json += F("},\"status\":{\"stringValue\":\"");
      json += FillStatus(fill_levels.paper);
      json += F("\"}}}},");

      json += F("\"plastic\":{\"mapValue\":{\"fields\":{" 
                "\"fill_percent\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.plastic);
      json += F("},\"status\":{\"stringValue\":\"");
      json += FillStatus(fill_levels.plastic);
      json += F("\"}}}}"); // status, plastic fields/map/value
      json += F("}}}");     // compartments fields/map/value
      json += F("}}");      // document fields and document
      return json;
    }

    String BuildEventDocumentJson(const CloudRecognition &recognition,
                                  const CompartmentFillLevels &fill_levels,
                                  const char *const timestamp,
                                  const String &image_url,
                                  const String &document_name)
    {
      const bool classified = recognition.has_classification &&
                              recognition.waste_type != nullptr;
      String json;
      json.reserve(1500);
      json += F("{\"name\":\"");
      json += document_name;
      json += F("\",\"fields\":{");
      json += F("\"event_type\":{\"stringValue\":\"");
      json += classified ? "CLASSIFY" : "ERROR";
      json += F("\"},\"waste_type\":{");
      if (classified)
      {
        json += F("\"stringValue\":\"");
        json += recognition.waste_type;
        json += '"';
      }
      else
      {
        json += F("\"nullValue\":null");
      }
      json += F("},\"target_compartment\":{");
      if (classified)
      {
        json += F("\"stringValue\":\"");
        json += recognition.waste_type;
        json += '"';
      }
      else
      {
        json += F("\"nullValue\":null");
      }
      json += F("},\"ai_confidence\":{");
      if (classified)
      {
        json += F("\"doubleValue\":");
        json += String(recognition.confidence, 6);
      }
      else
      {
        json += F("\"nullValue\":null");
      }
      json += F("},\"fill_percent\":{\"mapValue\":{\"fields\":{" 
                "\"organic\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.organic);
      json += F("},\"paper\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.paper);
      json += F("},\"plastic\":{\"doubleValue\":");
      json += static_cast<unsigned>(fill_levels.plastic);
      json += F("}}}},\"alert_threshold\":{\"doubleValue\":");
      json += static_cast<unsigned>(network_config::kFullThresholdPercent);
      json += F("},\"device_timestamp\":{\"timestampValue\":\"");
      json += timestamp;
      json += F("\"},\"received_at\":{\"timestampValue\":\"");
      json += timestamp;
      json += F("\"},\"synced_late\":{\"booleanValue\":false},"
                "\"firmware_version\":{\"stringValue\":\"");
      json += network_config::kFirmwareVersion;
      json += F("\"},\"ai_model_version\":{\"stringValue\":\"");
      json += network_config::kAiModelVersion;
      json += F("\"},\"alert_status\":{\"nullValue\":null},"
                "\"resolved_at\":{\"nullValue\":null},"
                "\"resolved_by\":{\"nullValue\":null},\"image_url\":{");
      if (image_url.isEmpty())
      {
        json += F("\"nullValue\":null");
      }
      else
      {
        json += F("\"stringValue\":\"");
        json += JsonEscape(image_url.c_str());
        json += '"';
      }
      json += F("}}}");
      return json;
    }

    String BuildFirestoreCommitJson(const String &device_document,
                                    const String &event_document)
    {
      String json;
      json.reserve(device_document.length() + event_document.length() + 800U);
      json += F("{\"writes\":[{\"update\":");
      json += device_document;
      json += F(",\"updateMask\":{\"fieldPaths\":["
                "\"last_seen_at\","
                "\"firmware_version\","
                "\"ai_model_version\","
                "\"class_name\","
                "\"compartments.organic.fill_percent\","
                "\"compartments.organic.status\","
                "\"compartments.paper.fill_percent\","
                "\"compartments.paper.status\","
                "\"compartments.plastic.fill_percent\","
                "\"compartments.plastic.status\"]},"
                "\"currentDocument\":{\"exists\":true}},{\"update\":");
      json += event_document;
      json += F(",\"currentDocument\":{\"exists\":false}}]}");
      return json;
    }

    HttpResponse SendFirestoreRequest(const String &url,
                                      const esp_http_client_method_t method,
                                      const String &json)
    {
      String authorization = "Bearer ";
      authorization += g_firebase_id_token;
      const HttpResponse response = SendJsonRequest(
          url, method, json, authorization.c_str(), nullptr);
      if (!IsHttpSuccess(response.status_code) && !response.body.isEmpty())
      {
        String preview = response.body.substring(0, 300);
        preview.replace('\n', ' ');
        preview.replace('\r', ' ');
        Serial.printf("Firestore error: %s\n", preview.c_str());
      }
      return response;
    }

    String FirestoreCommitUrl()
    {
      String url = FirestoreDocumentsBaseUrl();
      url += ":commit";
      return url;
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

  bool SyncRecognitionToCloud(const CloudRecognition &recognition,
                              const CompartmentFillLevels &fill_levels)
  {
    if (!fill_levels.received)
    {
      Serial.println("Cloud sync skipped: Nano fill levels are missing");
      return false;
    }
    if (WiFi.status() != WL_CONNECTED)
    {
      Serial.println("Cloud sync skipped: Wi-Fi is offline");
      return false;
    }

    char timestamp[25]{};
    if (!GetUtcTimestamp(timestamp, sizeof(timestamp)) &&
        (!InitializeCloudClock() ||
         !GetUtcTimestamp(timestamp, sizeof(timestamp))))
    {
      Serial.println("Cloud sync skipped: UTC timestamp is unavailable");
      return false;
    }

    const String image_url = UploadToCloudinary(recognition);
    if (image_url.isEmpty())
    {
      Serial.println("Firestore sync cancelled: Cloudinary URL is unavailable");
      return false;
    }
    if (!EnsureFirebaseIdToken())
    {
      return false;
    }

    const String device_name = FirestoreDeviceDocumentName();
    char event_id[48]{};
    std::snprintf(event_id, sizeof(event_id), "evt_%lld_%08lx",
                  static_cast<long long>(std::time(nullptr)),
                  static_cast<unsigned long>(millis()));
    String event_name = device_name;
    event_name += "/events/";
    event_name += event_id;

    const String device_document = BuildDeviceDocumentJson(
        recognition, fill_levels, timestamp, device_name);
    const String event_document = BuildEventDocumentJson(
        recognition, fill_levels, timestamp, image_url, event_name);
    const String commit_json =
        BuildFirestoreCommitJson(device_document, event_document);

    HttpResponse commit_response = SendFirestoreRequest(
        FirestoreCommitUrl(), HTTP_METHOD_POST, commit_json);

    if (commit_response.status_code == 401)
    {
      g_firebase_id_token = "";
      g_firebase_token_valid_until_ms = 0;
      if (AcquireFirebaseIdToken())
      {
        commit_response = SendFirestoreRequest(
            FirestoreCommitUrl(), HTTP_METHOD_POST, commit_json);
      }
    }

    const bool committed = IsHttpSuccess(commit_response.status_code);
    Serial.printf("Firestore atomic commit: HTTP %d, event=%s\n",
                  commit_response.status_code, event_id);
    return committed;
  }
} // namespace aiot
