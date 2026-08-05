#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>

#include "image_preprocessor.h"

namespace {

constexpr std::size_t kWidth = 96U;
constexpr std::size_t kHeight = 96U;
constexpr std::size_t kChannels = 3U;
constexpr std::uint64_t kExpectedFnv1a = 0x670ca86ebce58acfULL;

}  // namespace

int main() {
  std::vector<std::uint8_t> source(kWidth * kHeight * kChannels);
  for (std::size_t y = 0U; y < kHeight; ++y) {
    for (std::size_t x = 0U; x < kWidth; ++x) {
      const std::size_t offset = (y * kWidth + x) * kChannels;
      source[offset] = static_cast<std::uint8_t>((3U * x + 5U * y + 17U) & 255U);
      source[offset + 1U] =
          static_cast<std::uint8_t>((7U * x + 2U * y + 41U) & 255U);
      source[offset + 2U] =
          static_cast<std::uint8_t>((11U * x + 13U * y + 73U) & 255U);
    }
  }

  aiot::ImagePreprocessor preprocessor;
  if (preprocessor.Configure(1.0F / 255.0F, -128) != aiot::Status::kOk) {
    std::cerr << "V8 preprocessor configure failed\n";
    return 1;
  }
  const aiot::ImageView view{
      source.data(), source.size(), kWidth * kChannels,
      static_cast<std::uint16_t>(kWidth), static_cast<std::uint16_t>(kHeight),
      aiot::PixelFormat::kRgb888};
  std::vector<std::int8_t> output(source.size());
  if (preprocessor.Run(view, output.data(), output.size()) != aiot::Status::kOk) {
    std::cerr << "V8 preprocessor run failed\n";
    return 1;
  }

  std::uint64_t hash = 1469598103934665603ULL;
  for (const std::int8_t value : output) {
    const auto pixel = static_cast<std::uint8_t>(
        static_cast<std::int16_t>(value) + 128);
    hash ^= pixel;
    hash *= 1099511628211ULL;
  }
  if (hash != kExpectedFnv1a) {
    std::cerr << "V8 preprocessing mismatch: 0x" << std::hex << hash
              << " != 0x" << kExpectedFnv1a << '\n';
    return 1;
  }
  std::cout << "V8 preprocessing contract: PASS\n";
  return 0;
}
