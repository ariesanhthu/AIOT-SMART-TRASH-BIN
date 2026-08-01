#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>

#include "image_preprocessor.h"

namespace {

constexpr std::size_t kWidth = 96U;
constexpr std::size_t kHeight = 96U;
constexpr std::size_t kChannels = 3U;

bool CheckRgb888Gray(const std::uint8_t input, const std::int8_t expected) {
  std::vector<std::uint8_t> source(kWidth * kHeight * kChannels, input);
  std::vector<std::int8_t> output(source.size());
  aiot::ImagePreprocessor preprocessor;
  if (preprocessor.Configure(1.0F / 255.0F, -128) != aiot::Status::kOk) {
    return false;
  }
  const aiot::ImageView view{
      source.data(), source.size(), kWidth * kChannels,
      static_cast<std::uint16_t>(kWidth), static_cast<std::uint16_t>(kHeight),
      aiot::PixelFormat::kRgb888};
  if (preprocessor.Run(view, output.data(), output.size()) != aiot::Status::kOk) {
    return false;
  }
  return std::all_of(output.begin(), output.end(),
                     [expected](const std::int8_t value) {
                       return value == expected;
                     });
}

bool CheckRgb565White() {
  std::vector<std::uint8_t> source(kWidth * kHeight * 2U);
  for (std::size_t index = 0; index < source.size(); index += 2U) {
    source[index] = 0xFFU;
    source[index + 1U] = 0xFFU;
  }
  std::vector<std::int8_t> output(kWidth * kHeight * kChannels);
  aiot::ImagePreprocessor preprocessor;
  if (preprocessor.Configure(1.0F / 255.0F, -128) != aiot::Status::kOk) {
    return false;
  }
  const aiot::ImageView view{
      source.data(), source.size(), kWidth * 2U,
      static_cast<std::uint16_t>(kWidth), static_cast<std::uint16_t>(kHeight),
      aiot::PixelFormat::kRgb565BigEndian};
  if (preprocessor.Run(view, output.data(), output.size()) != aiot::Status::kOk) {
    return false;
  }
  for (std::size_t index = 0; index < output.size(); index += 3U) {
    if (output[index] != 58 || output[index + 1U] != 61 ||
        output[index + 2U] != 58) {
      return false;
    }
  }
  return true;
}

}  // namespace

int main() {
  // Normal light is unchanged; dark/bright inputs use bounded Q8 gain.
  const bool passed = CheckRgb888Gray(128U, 0) &&
                      CheckRgb888Gray(64U, -43) &&
                      CheckRgb888Gray(200U, 32) && CheckRgb565White();
  if (!passed) {
    std::cerr << "V6 preprocessing contract test failed\n";
    return 1;
  }
  std::cout << "V6 preprocessing contract test passed\n";
  return 0;
}
