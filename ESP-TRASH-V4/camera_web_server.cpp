#include "camera_web_server.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "esp_http_server.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "img_converters.h"

#include "network_config.h"
#include "status.h"

namespace aiot {
namespace {

constexpr char kTag[] = "aiot_camera_web";
constexpr char kStreamContentType[] =
    "multipart/x-mixed-replace;boundary=frame";
constexpr char kStreamBoundary[] = "\r\n--frame\r\n";
constexpr char kStreamPart[] =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

CameraAdapter* g_camera = nullptr;
httpd_handle_t g_capture_server = nullptr;
httpd_handle_t g_stream_server = nullptr;

void SetCommonHeaders(httpd_req_t* const request) {
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control",
                     "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(request, "Pragma", "no-cache");
}

esp_err_t SendCameraError(httpd_req_t* const request, const Status status) {
  SetCommonHeaders(request);
  httpd_resp_set_status(request, status == Status::kCameraBusy
                                     ? "503 Service Unavailable"
                                     : "500 Internal Server Error");
  httpd_resp_set_type(request, "text/plain; charset=utf-8");
  return httpd_resp_sendstr(request, StatusName(status));
}

bool EncodeJpeg(camera_fb_t* const frame, std::uint8_t** const output,
                std::size_t* const output_length) {
  if (frame == nullptr || output == nullptr || output_length == nullptr) {
    return false;
  }
  return frame2jpg(frame, network_config::kWebJpegQuality, output,
                   output_length);
}

esp_err_t HealthHandler(httpd_req_t* const request) {
  SetCommonHeaders(request);
  httpd_resp_set_type(request, "application/json");
  return httpd_resp_sendstr(request, "{\"status\":\"ok\"}");
}

esp_err_t CaptureHandler(httpd_req_t* const request) {
  if (g_camera == nullptr) {
    return SendCameraError(request, Status::kNotInitialized);
  }

  Status status = Status::kOk;
  CameraFrameLease frame =
      g_camera->Capture(&status, network_config::kWebCaptureTimeoutMs);
  if (!frame || status != Status::kOk) {
    return SendCameraError(request, status);
  }

  std::uint8_t* jpeg = nullptr;
  std::size_t jpeg_length = 0U;
  const bool encoded = EncodeJpeg(frame.get(), &jpeg, &jpeg_length);
  frame.Reset();

  if (!encoded || jpeg == nullptr || jpeg_length == 0U) {
    std::free(jpeg);
    ESP_LOGE(kTag, "Snapshot JPEG conversion failed");
    return SendCameraError(request, Status::kCameraCaptureFailed);
  }

  SetCommonHeaders(request);
  httpd_resp_set_type(request, "image/jpeg");
  httpd_resp_set_hdr(request, "Content-Disposition",
                     "inline; filename=esp-trash-capture.jpg");
  const esp_err_t result = httpd_resp_send(
      request, reinterpret_cast<const char*>(jpeg), jpeg_length);
  std::free(jpeg);
  return result;
}

esp_err_t StreamHandler(httpd_req_t* const request) {
  if (g_camera == nullptr) {
    return SendCameraError(request, Status::kNotInitialized);
  }

  esp_err_t result = httpd_resp_set_type(request, kStreamContentType);
  if (result != ESP_OK) {
    return result;
  }
  SetCommonHeaders(request);
  httpd_resp_set_hdr(request, "X-Framerate",
                     network_config::kWebStreamFramerateHeader);

  while (result == ESP_OK) {
    Status status = Status::kOk;
    CameraFrameLease frame =
        g_camera->Capture(&status, network_config::kWebCaptureTimeoutMs);
    if (!frame || status != Status::kOk) {
      // The AI/UART path has priority whenever it owns the camera. A transient
      // timeout should drop one web frame instead of terminating the stream.
      vTaskDelay(pdMS_TO_TICKS(network_config::kWebStreamRetryDelayMs));
      continue;
    }

    std::uint8_t* jpeg = nullptr;
    std::size_t jpeg_length = 0U;
    const bool encoded = EncodeJpeg(frame.get(), &jpeg, &jpeg_length);
    frame.Reset();

    if (!encoded || jpeg == nullptr || jpeg_length == 0U) {
      std::free(jpeg);
      ESP_LOGW(kTag, "Stream JPEG conversion failed; dropping frame");
      vTaskDelay(pdMS_TO_TICKS(network_config::kWebStreamRetryDelayMs));
      continue;
    }

    char part_header[96]{};
    const int header_length =
        std::snprintf(part_header, sizeof(part_header), kStreamPart,
                      static_cast<unsigned>(jpeg_length));
    if (header_length <= 0 ||
        static_cast<std::size_t>(header_length) >= sizeof(part_header)) {
      std::free(jpeg);
      return ESP_FAIL;
    }

    result = httpd_resp_send_chunk(request, kStreamBoundary,
                                   std::strlen(kStreamBoundary));
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, part_header, header_length);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
          request, reinterpret_cast<const char*>(jpeg), jpeg_length);
    }
    std::free(jpeg);

    if (result == ESP_OK) {
      vTaskDelay(pdMS_TO_TICKS(network_config::kWebStreamFrameIntervalMs));
    }
  }

  ESP_LOGI(kTag, "MJPEG client disconnected");
  return result;
}

httpd_uri_t MakeUri(const char* const uri, esp_err_t (*handler)(httpd_req_t*)) {
  httpd_uri_t descriptor{};
  descriptor.uri = uri;
  descriptor.method = HTTP_GET;
  descriptor.handler = handler;
  descriptor.user_ctx = nullptr;
  return descriptor;
}

bool StartCaptureServer() {
  if (g_capture_server != nullptr) {
    return true;
  }

  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.lru_purge_enable = true;
  if (httpd_start(&g_capture_server, &config) != ESP_OK) {
    g_capture_server = nullptr;
    ESP_LOGE(kTag, "Unable to start capture server on port 80");
    return false;
  }

  const httpd_uri_t health_uri = MakeUri("/health", HealthHandler);
  const httpd_uri_t capture_uri = MakeUri("/capture", CaptureHandler);
  if (httpd_register_uri_handler(g_capture_server, &health_uri) != ESP_OK ||
      httpd_register_uri_handler(g_capture_server, &capture_uri) != ESP_OK) {
    httpd_stop(g_capture_server);
    g_capture_server = nullptr;
    ESP_LOGE(kTag, "Unable to register capture server routes");
    return false;
  }
  return true;
}

bool StartStreamServer() {
  if (g_stream_server != nullptr) {
    return true;
  }

  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port += 1;
  config.lru_purge_enable = true;
  if (httpd_start(&g_stream_server, &config) != ESP_OK) {
    g_stream_server = nullptr;
    ESP_LOGE(kTag, "Unable to start stream server on port 81");
    return false;
  }

  const httpd_uri_t stream_uri = MakeUri("/stream", StreamHandler);
  if (httpd_register_uri_handler(g_stream_server, &stream_uri) != ESP_OK) {
    httpd_stop(g_stream_server);
    g_stream_server = nullptr;
    ESP_LOGE(kTag, "Unable to register stream server route");
    return false;
  }
  return true;
}

}  // namespace

bool StartCameraWebServer(CameraAdapter* const camera) noexcept {
  if (camera == nullptr) {
    return false;
  }
  g_camera = camera;

  const bool capture_started = StartCaptureServer();
  const bool stream_started = StartStreamServer();
  if (capture_started && stream_started) {
    ESP_LOGI(kTag, "Camera web endpoints ready on ports 80 and 81");
  }
  return capture_started && stream_started;
}

}  // namespace aiot
