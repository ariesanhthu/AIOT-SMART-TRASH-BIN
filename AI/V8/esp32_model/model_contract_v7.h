#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace aiot::model_contract {

inline constexpr int kInputBatch = 1;
inline constexpr int kInputHeight = 96;
inline constexpr int kInputWidth = 96;
inline constexpr int kInputChannels = 3;
inline constexpr int kClassCount = 3;

inline constexpr float kExpectedInputScale = 0.0039215688593685627F;
inline constexpr std::int32_t kExpectedInputZeroPoint = -128;
inline constexpr float kExpectedOutputScale = 0.00390625F;
inline constexpr std::int32_t kExpectedOutputZeroPoint = -128;
inline constexpr float kQuantizationTolerance = 1.0e-7F;

inline constexpr int kExpectedModelBytes = 62560;
inline constexpr char kExpectedModelSha256[] = "12d9d1c5c16b72c1acd384fcc13004e652b435534c8fbf2a5e6219c980580c6d";

enum class OutputSemantic : std::uint8_t { kLogits, kProbabilities };
inline constexpr OutputSemantic kOutputSemantic = OutputSemantic::kProbabilities;

enum class WasteClass : std::uint8_t {
  kPaper = 0,
  kPlastic = 1,
  kOrganic = 2,
};
inline constexpr std::array<const char*, kClassCount> kLabels = {
    "paper", "plastic", "organic"};

// LiteRT deterministic startup reference raw output: [-128, 127, -128].
inline constexpr std::uint32_t kSelfTestMultiplier = 191U;
inline constexpr std::uint32_t kSelfTestOffset = 7U;
inline constexpr WasteClass kSelfTestExpectedClass = WasteClass::kPlastic;
inline constexpr int kSelfTestMinimumRawMargin = 127;

inline constexpr std::size_t kTensorArenaBytes = 256U * 1024U;

}  // namespace aiot::model_contract
