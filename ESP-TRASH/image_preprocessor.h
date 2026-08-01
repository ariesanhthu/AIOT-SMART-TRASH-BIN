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
// deterministic nearest-neighbor mapping, applies bounded mean-luminance
// normalization, and writes quantized values directly into the TFLM input
// tensor. Sampling offsets are cached and no heap allocation occurs.
class ImagePreprocessor final {
 public:
  ImagePreprocessor() = default;

  [[nodiscard]] Status Configure(float input_scale,
                                 std::int32_t input_zero_point) noexcept;
  [[nodiscard]] Status Run(const ImageView& source,
                           std::int8_t* destination,
                           std::size_t destination_bytes) noexcept;

 private:
  [[nodiscard]] Status BuildSamplingPlan(const ImageView& source,
                                         std::size_t bytes_per_pixel) noexcept;
  [[nodiscard]] Status RunRgb888(const ImageView& source,
                                 std::int8_t* destination) noexcept;
  [[nodiscard]] Status RunRgb565(const ImageView& source,
                                 bool big_endian,
                                 std::int8_t* destination) noexcept;

  std::array<std::size_t, model_contract::kInputWidth> x_byte_offsets_{};
  std::array<std::size_t, model_contract::kInputHeight> y_byte_offsets_{};
  std::size_t cached_stride_bytes_ = 0U;
  std::uint16_t cached_width_ = 0U;
  std::uint16_t cached_height_ = 0U;
  std::uint8_t cached_bytes_per_pixel_ = 0U;
  bool sampling_plan_valid_ = false;
  bool configured_ = false;
};

}  // namespace aiot
