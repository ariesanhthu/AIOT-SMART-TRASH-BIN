#include "tflm_classifier.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "model_data.h"

namespace aiot {
namespace {

constexpr char kTag[] = "aiot_tflm";

static_assert(model_contract::kTensorArenaBytes % 16U == 0U,
              "Tensor arena must preserve SIMD alignment");

[[nodiscard]] bool HasShape(const TfLiteTensor& tensor,
                            const int dimensions,
                            const int* const expected) noexcept {
  if (tensor.dims == nullptr || tensor.dims->size != dimensions) {
    return false;
  }
  for (int index = 0; index < dimensions; ++index) {
    if (tensor.dims->data[index] != expected[index]) {
      return false;
    }
  }
  return true;
}

}  // namespace

TflmClassifier::~TflmClassifier() {
  if (interpreter_ != nullptr) {
    interpreter_->~MicroInterpreter();
    interpreter_ = nullptr;
  }
  if (tensor_arena_ != nullptr) {
    heap_caps_free(tensor_arena_);
    tensor_arena_ = nullptr;
  }
}

Status TflmClassifier::RegisterOperators() noexcept {
  if (operators_registered_) {
    return Status::kOk;
  }

  // Exact V9 inventory: CONV_2D x5, MEAN, FULLY_CONNECTED and SOFTMAX.
  // Registering only unique operators keeps unused kernels out of flash.
  if (resolver_.AddConv2D() != kTfLiteOk ||
      resolver_.AddMean() != kTfLiteOk ||
      resolver_.AddFullyConnected() != kTfLiteOk ||
      resolver_.AddSoftmax() != kTfLiteOk) {
    return Status::kOperatorRegistrationFailed;
  }

  operators_registered_ = true;
  return Status::kOk;
}

Status TflmClassifier::Initialize() noexcept {
  if (initialized_) {
    return Status::kAlreadyInitialized;
  }
  if (g_model_len != model_contract::kExpectedModelBytes ||
      std::strcmp(g_model_sha256, model_contract::kExpectedModelSha256) != 0) {
    ESP_LOGE(kTag, "Embedded model does not match V9 contract");
    return Status::kInvalidModel;
  }

  model_ = tflite::GetModel(g_model);
  if (model_ == nullptr) {
    return Status::kInvalidModel;
  }
  if (model_->version() != TFLITE_SCHEMA_VERSION) {
    ESP_LOGE(kTag, "Model schema %ld != runtime schema %d",
             static_cast<long>(model_->version()), TFLITE_SCHEMA_VERSION);
    return Status::kModelSchemaMismatch;
  }

  const Status registration_status = RegisterOperators();
  if (registration_status != Status::kOk) {
    return registration_status;
  }

  // Arduino-ESP32 does not place a large static BSS object in PSRAM by
  // default. Allocate the one lifetime-long, 16-byte aligned arena explicitly
  // from PSRAM. There is still no per-inference allocation or fragmentation.
  tensor_arena_ = static_cast<std::uint8_t*>(heap_caps_aligned_alloc(
      16U, model_contract::kTensorArenaBytes,
      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (tensor_arena_ == nullptr) {
    ESP_LOGE(kTag, "Unable to allocate %u-byte tensor arena in PSRAM",
             static_cast<unsigned>(model_contract::kTensorArenaBytes));
    return Status::kPsramUnavailable;
  }

  // Placement construction avoids new/delete while still giving the adapter
  // deterministic RAII teardown semantics.
  interpreter_ = new (interpreter_storage_) tflite::MicroInterpreter(
      model_, resolver_, tensor_arena_, model_contract::kTensorArenaBytes);
  if (interpreter_->AllocateTensors() != kTfLiteOk) {
    interpreter_->~MicroInterpreter();
    interpreter_ = nullptr;
    heap_caps_free(tensor_arena_);
    tensor_arena_ = nullptr;
    return Status::kTensorAllocationFailed;
  }

  if (interpreter_->inputs_size() != 1U ||
      interpreter_->outputs_size() != 1U) {
    interpreter_->~MicroInterpreter();
    interpreter_ = nullptr;
    heap_caps_free(tensor_arena_);
    tensor_arena_ = nullptr;
    return Status::kTensorContractMismatch;
  }

  input_ = interpreter_->input(0);
  output_ = interpreter_->output(0);
  const Status contract_status = ValidateTensorContract();
  if (contract_status != Status::kOk) {
    interpreter_->~MicroInterpreter();
    interpreter_ = nullptr;
    input_ = nullptr;
    output_ = nullptr;
    heap_caps_free(tensor_arena_);
    tensor_arena_ = nullptr;
    return contract_status;
  }

  const Status self_test_status = RunModelSelfTest();
  if (self_test_status != Status::kOk) {
    interpreter_->~MicroInterpreter();
    interpreter_ = nullptr;
    input_ = nullptr;
    output_ = nullptr;
    heap_caps_free(tensor_arena_);
    tensor_arena_ = nullptr;
    return self_test_status;
  }

  arena_used_bytes_ = interpreter_->arena_used_bytes();
  initialized_ = true;
  ESP_LOGI(kTag, "model=%d bytes sha256=%s arena=%u/%u bytes", g_model_len,
           g_model_sha256,
           static_cast<unsigned>(arena_used_bytes_),
           static_cast<unsigned>(model_contract::kTensorArenaBytes));
  return Status::kOk;
}

Status TflmClassifier::ValidateTensorContract() noexcept {
  if (input_ == nullptr || output_ == nullptr || input_->data.int8 == nullptr ||
      output_->data.int8 == nullptr) {
    return Status::kTensorContractMismatch;
  }

  constexpr int kExpectedInputShape[] = {
      model_contract::kInputBatch, model_contract::kInputHeight,
      model_contract::kInputWidth, model_contract::kInputChannels};
  constexpr int kExpectedOutputShape[] = {model_contract::kInputBatch,
                                           model_contract::kClassCount};

  if (input_->type != kTfLiteInt8 ||
      !HasShape(*input_, 4, kExpectedInputShape) ||
      input_->bytes < static_cast<std::size_t>(model_contract::kInputHeight) *
                          model_contract::kInputWidth *
                          model_contract::kInputChannels) {
    return Status::kTensorContractMismatch;
  }
  if (output_->type != kTfLiteInt8 ||
      !HasShape(*output_, 2, kExpectedOutputShape) ||
      output_->bytes < static_cast<std::size_t>(model_contract::kClassCount)) {
    return Status::kTensorContractMismatch;
  }

  if (!std::isfinite(input_->params.scale) ||
      std::fabs(input_->params.scale - model_contract::kExpectedInputScale) >
          model_contract::kQuantizationTolerance ||
      input_->params.zero_point != model_contract::kExpectedInputZeroPoint) {
    ESP_LOGE(kTag, "Input quantization mismatch: scale=%g zero_point=%ld",
             static_cast<double>(input_->params.scale),
             static_cast<long>(input_->params.zero_point));
    return Status::kTensorContractMismatch;
  }
  if (!std::isfinite(output_->params.scale) ||
      std::fabs(output_->params.scale -
                model_contract::kExpectedOutputScale) >
          model_contract::kQuantizationTolerance ||
      output_->params.zero_point !=
          model_contract::kExpectedOutputZeroPoint) {
    ESP_LOGE(kTag, "Output quantization mismatch: scale=%g zero_point=%ld",
             static_cast<double>(output_->params.scale),
             static_cast<long>(output_->params.zero_point));
    return Status::kTensorContractMismatch;
  }

  return Status::kOk;
}

Status TflmClassifier::RunModelSelfTest() noexcept {
  // Deterministic synthetic input costs no flash asset and proves that this
  // exact model can execute through the on-device quantized kernels. Requiring
  // the same well-separated top class tolerates kernel-specific rounding.
  std::int8_t* value = input_->data.int8;
  std::int8_t* const end = value + input_->bytes;
  std::uint32_t index = 0U;
  while (value != end) {
    const std::uint8_t channel = static_cast<std::uint8_t>(
        (index * model_contract::kSelfTestMultiplier +
         model_contract::kSelfTestOffset) &
        0xFFU);
    *value++ = static_cast<std::int8_t>(
        static_cast<std::int16_t>(channel) - 128);
    ++index;
  }

  if (interpreter_->Invoke() != kTfLiteOk) {
    ESP_LOGE(kTag, "Model self-test invoke failed");
    return Status::kModelSelfTestFailed;
  }

  const std::size_t expected_index = static_cast<std::size_t>(
      model_contract::kSelfTestExpectedClass);
  const int expected_value = static_cast<int>(output_->data.int8[expected_index]);
  ESP_LOGI(kTag, "self-test raw=[%d,%d,%d] expected_top=%s",
           static_cast<int>(output_->data.int8[0]),
           static_cast<int>(output_->data.int8[1]),
           static_cast<int>(output_->data.int8[2]),
           model_contract::kLabels[expected_index]);
  for (std::size_t class_index = 0U;
       class_index < static_cast<std::size_t>(model_contract::kClassCount);
       ++class_index) {
    if (class_index == expected_index) {
      continue;
    }
    const int margin =
        expected_value - static_cast<int>(output_->data.int8[class_index]);
    if (margin < model_contract::kSelfTestMinimumRawMargin) {
      ESP_LOGE(kTag, "Model self-test output mismatch");
      return Status::kModelSelfTestFailed;
    }
  }
  return Status::kOk;
}

TfLiteTensor* TflmClassifier::input_tensor() noexcept {
  return initialized_ ? input_ : nullptr;
}

Status TflmClassifier::Classify(ClassificationResult* const result) noexcept {
  if (result == nullptr) {
    return Status::kInvalidArgument;
  }
  if (!initialized_ || interpreter_ == nullptr) {
    return Status::kNotInitialized;
  }

  const std::int64_t start_us = esp_timer_get_time();
  if (interpreter_->Invoke() != kTfLiteOk) {
    return Status::kInvokeFailed;
  }
  result->inference_time_us = esp_timer_get_time() - start_us;
  return Postprocess(*output_, result);
}

Status TflmClassifier::Postprocess(
    const TfLiteTensor& output,
    ClassificationResult* const result) const noexcept {
  float values[model_contract::kClassCount]{};
  const std::int8_t* source = output.data.int8;
  float* value = values;
  float* const values_end = values + model_contract::kClassCount;
  while (value != values_end) {
    *value++ =
        static_cast<float>(*source++ - output.params.zero_point) *
        output.params.scale;
  }

  float probability_sum = 0.0F;
  if constexpr (model_contract::kOutputSemantic ==
                model_contract::OutputSemantic::kLogits) {
    const float maximum = *std::max_element(values, values_end);
    value = values;
    while (value != values_end) {
      *value = std::exp(*value - maximum);
      probability_sum += *value++;
    }
  } else {
    value = values;
    while (value != values_end) {
      *value = std::clamp(*value, 0.0F, 1.0F);
      probability_sum += *value++;
    }
  }

  if (!std::isfinite(probability_sum) || probability_sum <= 0.0F) {
    return Status::kPostprocessFailed;
  }

  float* probability = result->probabilities.data();
  const float* value_reader = values;
  const float* const value_end = values + model_contract::kClassCount;
  while (value_reader != value_end) {
    *probability++ = *value_reader++ / probability_sum;
  }

  const auto maximum = std::max_element(result->probabilities.begin(),
                                        result->probabilities.end());
  const std::size_t class_index = static_cast<std::size_t>(
      maximum - result->probabilities.begin());
  result->predicted =
      static_cast<model_contract::WasteClass>(class_index);
  result->confidence = *maximum;
  return Status::kOk;
}

const char* ClassName(const model_contract::WasteClass waste_class) noexcept {
  const std::size_t index = static_cast<std::size_t>(waste_class);
  return index < model_contract::kLabels.size()
             ? model_contract::kLabels[index]
             : "invalid";
}

}  // namespace aiot
