#include <cinttypes>
#include <cstddef>
#include <cstdint>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "camera_adapter.h"
#include "image_preprocessor.h"
#include "status.h"
#include "tflm_classifier.h"

namespace {

constexpr char kTag[] = "aiot_app";

void LogMemory(const char* const stage) noexcept {
  ESP_LOGI(kTag,
           "%s: internal_free=%u internal_largest=%u psram_free=%u "
           "psram_largest=%u",
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

[[noreturn]] void SafeIdle(const aiot::Status status) noexcept {
  ESP_LOGE(kTag, "Entering fail-safe idle: %s", aiot::StatusName(status));
  for (;;) {
    // No actuator is commanded from this scaffold. Integrate the physical
    // controller only after it also treats this state as "all gates closed".
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

}  // namespace

extern "C" void app_main() {
  static aiot::TflmClassifier classifier;
  static aiot::ImagePreprocessor preprocessor;
  static aiot::CameraAdapter camera;

  LogMemory("boot");

  aiot::Status status = classifier.Initialize();
  if (status != aiot::Status::kOk) {
    SafeIdle(status);
  }

  TfLiteTensor* const input = classifier.input_tensor();
  if (input == nullptr) {
    SafeIdle(aiot::Status::kTensorContractMismatch);
  }
  status = preprocessor.Configure(input->params.scale, input->params.zero_point);
  if (status != aiot::Status::kOk) {
    SafeIdle(status);
  }

  status = camera.Initialize();
  if (status != aiot::Status::kOk) {
    SafeIdle(status);
  }

  // Drop the first frames while auto-exposure settles. Move-only leases ensure
  // each buffer is returned even if the capture loop changes later.
  for (int warmup = 0; warmup < 2; ++warmup) {
    aiot::CameraFrameLease frame = camera.Capture(&status);
    if (!frame || status != aiot::Status::kOk) {
      SafeIdle(status);
    }
  }
  LogMemory("ready");

  for (;;) {
    // TODO(hardware integration): replace this periodic trigger with the object
    // presence event. Keep capture/preprocess/invoke serialized; TFLM and the
    // camera framebuffer are intentionally not accessed concurrently.
    {
      aiot::CameraFrameLease frame = camera.Capture(&status);
      if (!frame || status != aiot::Status::kOk) {
        ESP_LOGE(kTag, "Capture failed: %s", aiot::StatusName(status));
        vTaskDelay(pdMS_TO_TICKS(250));
        continue;
      }

      aiot::ImageView view{};
      status = aiot::CameraAdapter::MakeImageView(*frame.get(), &view);
      if (status == aiot::Status::kOk) {
        status = preprocessor.Run(view, input->data.int8, input->bytes);
      }
      // frame is returned here, before Invoke(), reducing camera-buffer hold
      // time and making peak PSRAM ownership explicit.
    }

    if (status != aiot::Status::kOk) {
      ESP_LOGE(kTag, "Preprocess failed: %s", aiot::StatusName(status));
      vTaskDelay(pdMS_TO_TICKS(250));
      continue;
    }

    aiot::ClassificationResult result{};
    status = classifier.Classify(&result);
    if (status != aiot::Status::kOk) {
      ESP_LOGE(kTag, "Inference failed: %s", aiot::StatusName(status));
      vTaskDelay(pdMS_TO_TICKS(250));
      continue;
    }

    ESP_LOGI(kTag,
             "class=%s confidence=%.4f p=[%.4f,%.4f,%.4f] inference=%" PRId64
             " us",
             aiot::ClassName(result.predicted),
             static_cast<double>(result.confidence),
             static_cast<double>(result.probabilities[0]),
             static_cast<double>(result.probabilities[1]),
             static_cast<double>(result.probabilities[2]),
             result.inference_time_us);

    vTaskDelay(pdMS_TO_TICKS(2000));
  }
}
