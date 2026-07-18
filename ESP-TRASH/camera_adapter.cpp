#include "camera_adapter.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <utility>

#include "esp_heap_caps.h"
#include "esp_log.h"

namespace aiot {
namespace {

constexpr char kTag[] = "aiot_camera";

// Ai-Thinker ESP32-CAM + OV2640 pin map. GPIOs used here must not be reused by
// servos or ultrasonic sensors; use a second controller for those peripherals.
constexpr int kPinPowerDown = 32;
constexpr int kPinReset = -1;
constexpr int kPinXclk = 0;
constexpr int kPinSccbSda = 26;
constexpr int kPinSccbScl = 27;
constexpr int kPinD7 = 35;
constexpr int kPinD6 = 34;
constexpr int kPinD5 = 39;
constexpr int kPinD4 = 36;
constexpr int kPinD3 = 21;
constexpr int kPinD2 = 19;
constexpr int kPinD1 = 18;
constexpr int kPinD0 = 5;
constexpr int kPinVsync = 25;
constexpr int kPinHref = 23;
constexpr int kPinPclk = 22;

}  // namespace

CameraFrameLease::~CameraFrameLease() { Reset(); }

CameraFrameLease::CameraFrameLease(CameraFrameLease&& other) noexcept
    : frame_(std::exchange(other.frame_, nullptr)),
      mutex_(std::exchange(other.mutex_, nullptr)) {}

CameraFrameLease& CameraFrameLease::operator=(CameraFrameLease&& other) noexcept {
  if (this != &other) {
    Reset();
    frame_ = std::exchange(other.frame_, nullptr);
    mutex_ = std::exchange(other.mutex_, nullptr);
  }
  return *this;
}

void CameraFrameLease::Reset() noexcept {
  if (frame_ != nullptr) {
    esp_camera_fb_return(frame_);
    frame_ = nullptr;
  }
  if (mutex_ != nullptr) {
    xSemaphoreGive(mutex_);
    mutex_ = nullptr;
  }
}

CameraAdapter::~CameraAdapter() {
  if (initialized_) {
    esp_camera_deinit();
  }
  if (mutex_ != nullptr) {
    vSemaphoreDelete(mutex_);
    mutex_ = nullptr;
  }
}

Status CameraAdapter::Initialize() noexcept {
  if (initialized_) {
    return Status::kAlreadyInitialized;
  }
  if (heap_caps_get_total_size(MALLOC_CAP_SPIRAM) == 0U) {
    ESP_LOGE(kTag, "External PSRAM is required but was not detected");
    return Status::kPsramUnavailable;
  }

  mutex_ = xSemaphoreCreateMutex();
  if (mutex_ == nullptr) {
    ESP_LOGE(kTag, "Unable to create camera mutex");
    return Status::kCameraInitFailed;
  }

  // Assign fields individually instead of using a C++ designated initializer;
  // this keeps optional fields added by newer esp32-camera versions isolated in
  // this adapter.
  camera_config_t config{};
  config.pin_pwdn = kPinPowerDown;
  config.pin_reset = kPinReset;
  config.pin_xclk = kPinXclk;
  config.pin_sccb_sda = kPinSccbSda;
  config.pin_sccb_scl = kPinSccbScl;
  config.pin_d7 = kPinD7;
  config.pin_d6 = kPinD6;
  config.pin_d5 = kPinD5;
  config.pin_d4 = kPinD4;
  config.pin_d3 = kPinD3;
  config.pin_d2 = kPinD2;
  config.pin_d1 = kPinD1;
  config.pin_d0 = kPinD0;
  config.pin_vsync = kPinVsync;
  config.pin_href = kPinHref;
  config.pin_pclk = kPinPclk;
  config.xclk_freq_hz = 20'000'000;
  config.ledc_timer = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;

  // QVGA RGB565 is the maximum uncompressed size recommended for the original
  // ESP32. A single PSRAM framebuffer avoids continuous capture and eliminates
  // all per-frame allocation in application code.
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  const esp_err_t error = esp_camera_init(&config);
  if (error != ESP_OK) {
    ESP_LOGE(kTag, "esp_camera_init failed: %s", esp_err_to_name(error));
    vSemaphoreDelete(mutex_);
    mutex_ = nullptr;
    return Status::kCameraInitFailed;
  }

  initialized_ = true;
  return Status::kOk;
}

CameraFrameLease CameraAdapter::Capture(Status* const status,
                                        const std::uint32_t timeout_ms) noexcept {
  if (status == nullptr) {
    return CameraFrameLease{};
  }
  if (!initialized_) {
    *status = Status::kNotInitialized;
    return CameraFrameLease{};
  }
  if (mutex_ == nullptr ||
      xSemaphoreTake(mutex_, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
    *status = Status::kCameraBusy;
    return CameraFrameLease{};
  }

  camera_fb_t* const frame = esp_camera_fb_get();
  if (frame == nullptr) {
    xSemaphoreGive(mutex_);
    *status = Status::kCameraCaptureFailed;
    return CameraFrameLease{};
  }

  *status = Status::kOk;
  return CameraFrameLease{frame, mutex_};
}

Status CameraAdapter::MakeImageView(const camera_fb_t& frame,
                                    ImageView* const view) noexcept {
  if (view == nullptr || frame.buf == nullptr || frame.width == 0U ||
      frame.height == 0U) {
    return Status::kInvalidArgument;
  }

  std::size_t bytes_per_pixel = 0U;
  PixelFormat pixel_format{};
  switch (frame.format) {
    case PIXFORMAT_RGB565:
      bytes_per_pixel = 2U;
      // esp32-camera stores RGB565 as high byte then low byte. Keeping this in
      // the camera adapter makes a future driver byte-order change local.
      pixel_format = PixelFormat::kRgb565BigEndian;
      break;
    case PIXFORMAT_RGB888:
      bytes_per_pixel = 3U;
      pixel_format = PixelFormat::kRgb888;
      break;
    default:
      return Status::kUnsupportedPixelFormat;
  }

  const std::size_t width = frame.width;
  const std::size_t height = frame.height;
  if (width > std::numeric_limits<std::uint16_t>::max() ||
      height > std::numeric_limits<std::uint16_t>::max() ||
      width > std::numeric_limits<std::size_t>::max() / bytes_per_pixel) {
    return Status::kInvalidImageBuffer;
  }
  const std::size_t stride = width * bytes_per_pixel;
  if (height > frame.len / stride) {
    return Status::kInvalidImageBuffer;
  }

  view->data = frame.buf;
  view->length_bytes = frame.len;
  view->stride_bytes = stride;
  view->width = static_cast<std::uint16_t>(frame.width);
  view->height = static_cast<std::uint16_t>(frame.height);
  view->format = pixel_format;
  return Status::kOk;
}

}  // namespace aiot
