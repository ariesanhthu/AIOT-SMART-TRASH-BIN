#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace aiot::model_contract {

// Keep this file synchronized with labels.json and quantization.json generated
// from the final three-class model. Firmware deliberately fails closed when the
// embedded model does not satisfy this contract.
inline constexpr int kInputBatch = 1;
inline constexpr int kInputHeight = 96;
inline constexpr int kInputWidth = 96;
inline constexpr int kInputChannels = 3;
inline constexpr int kClassCount = 3;

inline constexpr float kExpectedInputScale = 1.0F / 255.0F;
inline constexpr std::int32_t kExpectedInputZeroPoint = -128;
inline constexpr float kExpectedOutputScale = 0.05487526208162308F;
inline constexpr std::int32_t kExpectedOutputZeroPoint = -27;
inline constexpr float kQuantizationTolerance = 1.0e-7F;

inline constexpr int kExpectedModelBytes = 62496;
inline constexpr char kExpectedModelSha256[] =
    "5e543adfcd64a5627015e0e770fa8b1638d1febaefea2f105fb383707019826a";

// This scaffold expects the Dense head to export logits. The firmware applies
// a stable softmax to only three values. Change to kProbabilities only if the
// final TFLite graph itself contains SOFTMAX.
enum class OutputSemantic : std::uint8_t {
  kLogits,
  kProbabilities,
};
inline constexpr OutputSemantic kOutputSemantic = OutputSemantic::kLogits;

enum class WasteClass : std::uint8_t {
  kPaper = 0,
  kPlastic = 1,
  kOrganic = 2,
};

inline constexpr std::array<const char*, kClassCount> kLabels = {
    "paper", "plastic", "organic"};

// One lifetime-long arena is allocated in external PSRAM. Keep headroom for
// the ESP-NN Conv2D scratch buffers; no allocation happens per inference.
inline constexpr std::size_t kTensorArenaBytes = 256U * 1024U;

}  // namespace aiot::model_contract
