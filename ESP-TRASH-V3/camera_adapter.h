#pragma once

#include <cstdint>

#include "esp_camera.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "image_preprocessor.h"
#include "status.h"

namespace aiot {

// Move-only ownership wrapper. Every successful esp_camera_fb_get() is paired
// with exactly one esp_camera_fb_return(), including early-return error paths.
class CameraFrameLease final {
 public:
  CameraFrameLease() noexcept = default;
  CameraFrameLease(camera_fb_t* frame, SemaphoreHandle_t mutex) noexcept
      : frame_(frame), mutex_(mutex) {}
  ~CameraFrameLease();

  CameraFrameLease(const CameraFrameLease&) = delete;
  CameraFrameLease& operator=(const CameraFrameLease&) = delete;
  CameraFrameLease(CameraFrameLease&& other) noexcept;
  CameraFrameLease& operator=(CameraFrameLease&& other) noexcept;

  [[nodiscard]] camera_fb_t* get() const noexcept { return frame_; }
  [[nodiscard]] explicit operator bool() const noexcept {
    return frame_ != nullptr;
  }
  void Reset() noexcept;

 private:
  camera_fb_t* frame_ = nullptr;
  SemaphoreHandle_t mutex_ = nullptr;
};

class CameraAdapter final {
 public:
  CameraAdapter() = default;
  ~CameraAdapter();

  CameraAdapter(const CameraAdapter&) = delete;
  CameraAdapter& operator=(const CameraAdapter&) = delete;

  [[nodiscard]] Status Initialize() noexcept;
  [[nodiscard]] CameraFrameLease Capture(Status* status,
                                         std::uint32_t timeout_ms = 1000U) noexcept;
  // CAMERA_GRAB_WHEN_EMPTY may keep the first queued framebuffer from well
  // before a trigger. Keep the camera mutex while discarding queued frames and
  // waiting for the final frame so the web stream cannot interleave a capture.
  // When not_before_us is non-zero, frames timestamped before that monotonic
  // time are also returned to the driver instead of being exposed to callers.
  [[nodiscard]] CameraFrameLease CaptureFresh(
      Status* status, std::uint8_t discard_frames = 1U,
      std::uint64_t not_before_us = 0U,
      std::uint32_t timeout_ms = 1000U) noexcept;
  [[nodiscard]] static Status MakeImageView(const camera_fb_t& frame,
                                            ImageView* view) noexcept;

 private:
  bool initialized_ = false;
  SemaphoreHandle_t mutex_ = nullptr;
};

}  // namespace aiot
