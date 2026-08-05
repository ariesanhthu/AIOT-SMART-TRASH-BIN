#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "model_contract.h"
#include "status.h"
#include "tensorflow/lite/c/common.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace aiot {

struct ClassificationResult {
  model_contract::WasteClass predicted = model_contract::WasteClass::kInvalid;
  std::array<float, model_contract::kClassCount> probabilities{};
  float confidence = 0.0F;
  std::int64_t inference_time_us = 0;
};

class TflmClassifier final {
 public:
  TflmClassifier() = default;
  ~TflmClassifier();

  TflmClassifier(const TflmClassifier&) = delete;
  TflmClassifier& operator=(const TflmClassifier&) = delete;

  [[nodiscard]] Status Initialize() noexcept;
  [[nodiscard]] Status Classify(ClassificationResult* result) noexcept;
  [[nodiscard]] TfLiteTensor* input_tensor() noexcept;
  [[nodiscard]] std::size_t arena_used_bytes() const noexcept {
    return arena_used_bytes_;
  }

 private:
  static constexpr int kRegisteredOperatorCount = 4;

  [[nodiscard]] Status RegisterOperators() noexcept;
  [[nodiscard]] Status ValidateTensorContract() noexcept;
  [[nodiscard]] Status RunModelSelfTest() noexcept;
  [[nodiscard]] Status Postprocess(const TfLiteTensor& output,
                                   ClassificationResult* result) const noexcept;

  const tflite::Model* model_ = nullptr;
  tflite::MicroMutableOpResolver<kRegisteredOperatorCount> resolver_{};
  alignas(tflite::MicroInterpreter)
      std::byte interpreter_storage_[sizeof(tflite::MicroInterpreter)]{};
  tflite::MicroInterpreter* interpreter_ = nullptr;
  std::uint8_t* tensor_arena_ = nullptr;
  TfLiteTensor* input_ = nullptr;
  TfLiteTensor* output_ = nullptr;
  std::size_t arena_used_bytes_ = 0;
  bool operators_registered_ = false;
  bool initialized_ = false;
};

[[nodiscard]] const char* ClassName(
    model_contract::WasteClass waste_class) noexcept;

}  // namespace aiot
