#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "model_contract.h"
#include "status.h"

namespace aiot {

enum class PixelFormat : std::uint8_t {
  kRgb888,
  kRgb565BigEndian,
  kRgb565LittleEndian,
};

struct ImageView {
  const std::uint8_t* data = nullptr;
  std::size_t length_bytes = 0;
  std::size_t stride_bytes = 0;
  std::uint16_t width = 0;
  std::uint16_t height = 0;
  PixelFormat format = PixelFormat::kRgb888;
};

// Center-crops an interleaved RGB image to a square, resizes it with a
// deterministic nearest-neighbor mapping, and writes quantized values directly
// into the TFLM input tensor. No heap allocation occurs in Configure() or Run().
class ImagePreprocessor final {
 public:
  ImagePreprocessor() = default;

  [[nodiscard]] Status Configure(float input_scale,
                                 std::int32_t input_zero_point) noexcept;
  [[nodiscard]] Status Run(const ImageView& source,
                           std::int8_t* destination,
                           std::size_t destination_bytes) noexcept;

 private:
  [[nodiscard]] Status RunRgb888(const ImageView& source,
                                 std::size_t crop_x,
                                 std::size_t crop_y,
                                 std::size_t crop_size,
                                 std::int8_t* destination) noexcept;
  [[nodiscard]] Status RunRgb565(const ImageView& source,
                                 std::size_t crop_x,
                                 std::size_t crop_y,
                                 std::size_t crop_size,
                                 bool big_endian,
                                 std::int8_t* destination) noexcept;
  void BuildHorizontalOffsets(std::size_t crop_x,
                              std::size_t crop_size,
                              std::size_t bytes_per_pixel) noexcept;

  std::array<std::int8_t, 256> quantization_lut_{};
  std::array<std::size_t, model_contract::kInputWidth> x_byte_offsets_{};
  float input_scale_ = 0.0F;
  std::int32_t input_zero_point_ = 0;
  bool configured_ = false;
};

}  // namespace aiot
