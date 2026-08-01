#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace aiot::model_contract {

// Keep this file synchronized with labels.json and quantization.json generated
// from the final four-class model. Firmware deliberately fails closed when the
// embedded model does not satisfy this contract.
inline constexpr int kInputBatch = 1;
inline constexpr int kInputHeight = 96;
inline constexpr int kInputWidth = 96;
inline constexpr int kInputChannels = 3;
inline constexpr int kClassCount = 4;

inline constexpr float kExpectedInputScale = 1.0F / 255.0F;
inline constexpr std::int32_t kExpectedInputZeroPoint = -128;
inline constexpr float kExpectedOutputScale = 0.064014412462711334F;
inline constexpr std::int32_t kExpectedOutputZeroPoint = -15;
inline constexpr float kQuantizationTolerance = 1.0e-7F;

inline constexpr int kExpectedModelBytes = 62816;
inline constexpr char kExpectedModelSha256[] =
    "efcc9b902c03e573d2a5fe7cd46127c8bfeee79dbbd676a179921f54ba2a6981";

// This scaffold expects the Dense head to export logits. The firmware applies
// a stable softmax to only four values. Change to kProbabilities only if the
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
  kOther = 3,
};

inline constexpr std::array<const char*, kClassCount> kLabels = {
    "paper", "plastic", "organic", "other"};

// LiteRT reference for the deterministic startup self-test is
// [-58, -58, -106, 127], whose top class is other with raw margin 185.
inline constexpr std::uint32_t kSelfTestMultiplier = 191U;
inline constexpr std::uint32_t kSelfTestOffset = 7U;
inline constexpr WasteClass kSelfTestExpectedClass = WasteClass::kOther;
inline constexpr int kSelfTestMinimumRawMargin = 64;

// One lifetime-long arena is allocated in external PSRAM. Keep headroom for
// the ESP-NN Conv2D scratch buffers; no allocation happens per inference.
inline constexpr std::size_t kTensorArenaBytes = 256U * 1024U;

}  // namespace aiot::model_contract
