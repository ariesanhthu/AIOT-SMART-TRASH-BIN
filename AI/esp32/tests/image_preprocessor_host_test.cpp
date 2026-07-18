#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>

#include "image_preprocessor.h"
#include "model_contract.h"
#include "status.h"

namespace {

constexpr std::size_t kOutputBytes =
    static_cast<std::size_t>(aiot::model_contract::kInputHeight) *
    aiot::model_contract::kInputWidth *
    aiot::model_contract::kInputChannels;

[[noreturn]] void Fail(const char* const message) {
  std::cerr << "FAILED: " << message << '\n';
  std::exit(1);
}

void Expect(const bool condition, const char* const message) {
  if (!condition) {
    Fail(message);
  }
}

constexpr std::int8_t QuantizeUnitPixel(const std::uint8_t pixel) {
  return static_cast<std::int8_t>(static_cast<int>(pixel) - 128);
}

std::size_t OutputOffset(const std::size_t y,
                         const std::size_t x,
                         const std::size_t channel) {
  return (y * aiot::model_contract::kInputWidth + x) * 3U + channel;
}

void TestRgb888CenterCropAndCanary() {
  // 4x2 -> centered 2x2 crop selects source columns 1 and 2. Each source
  // pixel has a distinct RGB triplet so both crop and nearest mapping are
  // observable at output quadrant boundaries.
  constexpr std::array<std::uint8_t, 4U * 2U * 3U> source = {
      1, 2, 3,     10, 20, 30,   40, 50, 60,   4, 5, 6,
      7, 8, 9,     70, 80, 90,   100, 110, 120, 11, 12, 13};

  aiot::ImagePreprocessor preprocessor;
  Expect(preprocessor.Configure(1.0F / 255.0F, -128) == aiot::Status::kOk,
         "RGB888 configure");

  aiot::ImageView view{};
  view.data = source.data();
  view.length_bytes = source.size();
  view.stride_bytes = 4U * 3U;
  view.width = 4;
  view.height = 2;
  view.format = aiot::PixelFormat::kRgb888;

  std::array<std::int8_t, kOutputBytes + 2U> guarded{};
  guarded.front() = 31;
  guarded.back() = 63;
  Expect(preprocessor.Run(view, guarded.data() + 1U, kOutputBytes) ==
             aiot::Status::kOk,
         "RGB888 run");
  Expect(guarded.front() == 31 && guarded.back() == 63,
         "RGB888 destination canary");

  const std::int8_t* const output = guarded.data() + 1U;
  Expect(output[OutputOffset(0, 0, 0)] == QuantizeUnitPixel(10) &&
             output[OutputOffset(0, 0, 1)] == QuantizeUnitPixel(20) &&
             output[OutputOffset(0, 0, 2)] == QuantizeUnitPixel(30),
         "RGB888 top-left sample");
  Expect(output[OutputOffset(47, 47, 0)] == QuantizeUnitPixel(10),
         "RGB888 first quadrant boundary");
  Expect(output[OutputOffset(48, 48, 0)] == QuantizeUnitPixel(100),
         "RGB888 second quadrant boundary");
  Expect(output[OutputOffset(95, 95, 0)] == QuantizeUnitPixel(100) &&
             output[OutputOffset(95, 95, 1)] == QuantizeUnitPixel(110) &&
             output[OutputOffset(95, 95, 2)] == QuantizeUnitPixel(120),
         "RGB888 bottom-right sample");
}

void TestRgb565ByteOrders() {
  // red, green / blue, white in RGB565.
  constexpr std::array<std::uint8_t, 8> big_endian = {
      0xF8, 0x00, 0x07, 0xE0, 0x00, 0x1F, 0xFF, 0xFF};
  constexpr std::array<std::uint8_t, 8> little_endian = {
      0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00, 0xFF, 0xFF};

  aiot::ImagePreprocessor preprocessor;
  Expect(preprocessor.Configure(1.0F / 255.0F, -128) == aiot::Status::kOk,
         "RGB565 configure");
  std::array<std::int8_t, kOutputBytes> expected{};
  std::array<std::int8_t, kOutputBytes> actual{};

  aiot::ImageView view{};
  view.data = big_endian.data();
  view.length_bytes = big_endian.size();
  view.stride_bytes = 4U;
  view.width = 2;
  view.height = 2;
  view.format = aiot::PixelFormat::kRgb565BigEndian;
  Expect(preprocessor.Run(view, expected.data(), expected.size()) ==
             aiot::Status::kOk,
         "RGB565 big-endian run");

  Expect(expected[OutputOffset(0, 0, 0)] == 127 &&
             expected[OutputOffset(0, 0, 1)] == -128 &&
             expected[OutputOffset(0, 0, 2)] == -128,
         "RGB565 red expansion");
  Expect(expected[OutputOffset(0, 95, 0)] == -128 &&
             expected[OutputOffset(0, 95, 1)] == 127 &&
             expected[OutputOffset(0, 95, 2)] == -128,
         "RGB565 green expansion");
  Expect(expected[OutputOffset(95, 0, 2)] == 127,
         "RGB565 blue expansion");
  Expect(expected[OutputOffset(95, 95, 0)] == 127 &&
             expected[OutputOffset(95, 95, 1)] == 127 &&
             expected[OutputOffset(95, 95, 2)] == 127,
         "RGB565 white expansion");

  view.data = little_endian.data();
  view.length_bytes = little_endian.size();
  view.format = aiot::PixelFormat::kRgb565LittleEndian;
  Expect(preprocessor.Run(view, actual.data(), actual.size()) ==
             aiot::Status::kOk,
         "RGB565 little-endian run");
  Expect(actual == expected, "RGB565 byte-order equivalence");
}

void TestBoundsChecks() {
  aiot::ImagePreprocessor preprocessor;
  Expect(preprocessor.Configure(0.0F, -128) ==
             aiot::Status::kInvalidArgument,
         "reject zero quantization scale");
  Expect(preprocessor.Configure(1.0F / 255.0F, -128) == aiot::Status::kOk,
         "bounds configure");

  constexpr std::array<std::uint8_t, 12> source{};
  std::array<std::int8_t, kOutputBytes> output{};
  aiot::ImageView view{};
  view.data = source.data();
  view.length_bytes = 11U;  // one byte shorter than stride * height
  view.stride_bytes = 6U;
  view.width = 2;
  view.height = 2;
  view.format = aiot::PixelFormat::kRgb888;
  Expect(preprocessor.Run(view, output.data(), output.size()) ==
             aiot::Status::kInvalidImageBuffer,
         "reject short source buffer");

  view.length_bytes = source.size();
  Expect(preprocessor.Run(view, output.data(), output.size() - 1U) ==
             aiot::Status::kInvalidArgument,
         "reject short destination buffer");
}

}  // namespace

int main() {
  TestRgb888CenterCropAndCanary();
  TestRgb565ByteOrders();
  TestBoundsChecks();
  std::cout << "image_preprocessor_host_test: PASS\n";
  return 0;
}
