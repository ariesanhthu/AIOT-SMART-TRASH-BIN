#include "image_preprocessor.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace aiot {
namespace {

constexpr std::size_t kDestinationBytes =
    static_cast<std::size_t>(model_contract::kInputHeight) *
    static_cast<std::size_t>(model_contract::kInputWidth) *
    static_cast<std::size_t>(model_contract::kInputChannels);

[[nodiscard]] constexpr std::uint8_t Expand5To8(
    const std::uint16_t value) noexcept {
  return static_cast<std::uint8_t>((value << 3U) | (value >> 2U));
}

[[nodiscard]] constexpr std::uint8_t Expand6To8(
    const std::uint16_t value) noexcept {
  return static_cast<std::uint8_t>((value << 2U) | (value >> 4U));
}

[[nodiscard]] bool IsValidSource(const ImageView& source,
                                 const std::size_t bytes_per_pixel) noexcept {
  if (source.data == nullptr || source.width == 0U || source.height == 0U) {
    return false;
  }

  const std::size_t width = source.width;
  if (width > std::numeric_limits<std::size_t>::max() / bytes_per_pixel) {
    return false;
  }
  const std::size_t minimum_stride = width * bytes_per_pixel;
  if (source.stride_bytes < minimum_stride || source.stride_bytes == 0U) {
    return false;
  }

  const std::size_t height = source.height;
  return height <= source.length_bytes / source.stride_bytes;
}

}  // namespace

Status ImagePreprocessor::Configure(const float input_scale,
                                    const std::int32_t input_zero_point) noexcept {
  const double maximum_quantized_magnitude =
      1.0 / static_cast<double>(input_scale) +
      std::fabs(static_cast<double>(input_zero_point));
  if (!std::isfinite(input_scale) || input_scale <= 0.0F ||
      input_zero_point < -128 || input_zero_point > 127 ||
      !std::isfinite(maximum_quantized_magnitude) ||
      maximum_quantized_magnitude >
          static_cast<double>(std::numeric_limits<long>::max())) {
    return Status::kInvalidArgument;
  }

  input_scale_ = input_scale;
  input_zero_point_ = input_zero_point;

  // Training maps each channel from uint8 [0, 255] to real [0, 1]. Build the
  // requantization table once; the per-pixel loop then performs only indexed
  // loads and pointer stores.
  std::int8_t* const lut_begin = quantization_lut_.data();
  for (std::size_t pixel = 0; pixel < quantization_lut_.size(); ++pixel) {
    const float real_value = static_cast<float>(pixel) / 255.0F;
    const long quantized =
        std::lround(real_value / input_scale_) + input_zero_point_;
    const long clamped = std::clamp(quantized, -128L, 127L);
    *(lut_begin + pixel) = static_cast<std::int8_t>(clamped);
  }

  configured_ = true;
  return Status::kOk;
}

Status ImagePreprocessor::Run(const ImageView& source,
                              std::int8_t* const destination,
                              const std::size_t destination_bytes) noexcept {
  if (!configured_) {
    return Status::kNotInitialized;
  }
  if (destination == nullptr || destination_bytes < kDestinationBytes) {
    return Status::kInvalidArgument;
  }

  std::size_t bytes_per_pixel = 0U;
  switch (source.format) {
    case PixelFormat::kRgb888:
      bytes_per_pixel = 3U;
      break;
    case PixelFormat::kRgb565BigEndian:
    case PixelFormat::kRgb565LittleEndian:
      bytes_per_pixel = 2U;
      break;
    default:
      return Status::kUnsupportedPixelFormat;
  }
  if (!IsValidSource(source, bytes_per_pixel)) {
    return Status::kInvalidImageBuffer;
  }

  const std::size_t width = source.width;
  const std::size_t height = source.height;
  const std::size_t crop_size = std::min(width, height);
  const std::size_t crop_x = (width - crop_size) / 2U;
  const std::size_t crop_y = (height - crop_size) / 2U;
  BuildHorizontalOffsets(crop_x, crop_size, bytes_per_pixel);

  switch (source.format) {
    case PixelFormat::kRgb888:
      return RunRgb888(source, crop_x, crop_y, crop_size, destination);
    case PixelFormat::kRgb565BigEndian:
      return RunRgb565(source, crop_x, crop_y, crop_size, true, destination);
    case PixelFormat::kRgb565LittleEndian:
      return RunRgb565(source, crop_x, crop_y, crop_size, false, destination);
    default:
      return Status::kUnsupportedPixelFormat;
  }
}

void ImagePreprocessor::BuildHorizontalOffsets(
    const std::size_t crop_x,
    const std::size_t crop_size,
    const std::size_t bytes_per_pixel) noexcept {
  std::size_t* offset = x_byte_offsets_.data();
  const std::size_t* const end = offset + x_byte_offsets_.size();
  std::size_t destination_x = 0U;
  while (offset != end) {
    // This floor mapping is intentionally identical to OpenCV INTER_NEAREST:
    // source_x = floor(destination_x * crop_size / destination_width).
    const std::size_t source_x =
        crop_x + (destination_x * crop_size) /
                     static_cast<std::size_t>(model_contract::kInputWidth);
    *offset++ = source_x * bytes_per_pixel;
    ++destination_x;
  }
}

Status ImagePreprocessor::RunRgb888(const ImageView& source,
                                    const std::size_t /*crop_x*/,
                                    const std::size_t crop_y,
                                    const std::size_t crop_size,
                                    std::int8_t* destination) noexcept {
  const std::int8_t* const lut = quantization_lut_.data();
  const std::size_t* const x_begin = x_byte_offsets_.data();
  const std::size_t* const x_end = x_begin + x_byte_offsets_.size();

  for (std::size_t destination_y = 0;
       destination_y < static_cast<std::size_t>(model_contract::kInputHeight);
       ++destination_y) {
    const std::size_t source_y =
        crop_y +
        (destination_y * crop_size) /
            static_cast<std::size_t>(model_contract::kInputHeight);
    const std::uint8_t* const row =
        source.data + source_y * source.stride_bytes;

    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel = row + *offset++;
      *destination++ = *(lut + pixel[0]);
      *destination++ = *(lut + pixel[1]);
      *destination++ = *(lut + pixel[2]);
    }
  }
  return Status::kOk;
}

Status ImagePreprocessor::RunRgb565(const ImageView& source,
                                    const std::size_t /*crop_x*/,
                                    const std::size_t crop_y,
                                    const std::size_t crop_size,
                                    const bool big_endian,
                                    std::int8_t* destination) noexcept {
  const std::int8_t* const lut = quantization_lut_.data();
  const std::size_t* const x_begin = x_byte_offsets_.data();
  const std::size_t* const x_end = x_begin + x_byte_offsets_.size();

  for (std::size_t destination_y = 0;
       destination_y < static_cast<std::size_t>(model_contract::kInputHeight);
       ++destination_y) {
    const std::size_t source_y =
        crop_y +
        (destination_y * crop_size) /
            static_cast<std::size_t>(model_contract::kInputHeight);
    const std::uint8_t* const row =
        source.data + source_y * source.stride_bytes;

    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel_bytes = row + *offset++;
      const std::uint16_t packed = big_endian
                                       ? static_cast<std::uint16_t>(
                                             (pixel_bytes[0] << 8U) |
                                             pixel_bytes[1])
                                       : static_cast<std::uint16_t>(
                                             (pixel_bytes[1] << 8U) |
                                             pixel_bytes[0]);

      const std::uint8_t red = Expand5To8((packed >> 11U) & 0x1FU);
      const std::uint8_t green = Expand6To8((packed >> 5U) & 0x3FU);
      const std::uint8_t blue = Expand5To8(packed & 0x1FU);
      *destination++ = *(lut + red);
      *destination++ = *(lut + green);
      *destination++ = *(lut + blue);
    }
  }
  return Status::kOk;
}

}  // namespace aiot
