#include "image_preprocessor.h"

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
  // Match Espressif's RGB565 -> JPEG conversion used to create the training
  // captures. Replicating the low bits changes the input distribution.
  return static_cast<std::uint8_t>(value << 3U);
}

[[nodiscard]] constexpr std::uint8_t Expand6To8(
    const std::uint16_t value) noexcept {
  return static_cast<std::uint8_t>(value << 2U);
}

[[nodiscard]] constexpr std::int8_t QuantizeRgbChannel(
    const std::uint8_t value) noexcept {
  // The V4 input contract is q = round((pixel / 255) / (1 / 255)) - 128.
  // Therefore every uint8 channel maps exactly to pixel - 128.
  return static_cast<std::int8_t>(
      static_cast<std::int16_t>(value) +
      model_contract::kExpectedInputZeroPoint);
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
  if (!std::isfinite(input_scale) || input_scale <= 0.0F ||
      std::fabs(input_scale - model_contract::kExpectedInputScale) >
          model_contract::kQuantizationTolerance ||
      input_zero_point != model_contract::kExpectedInputZeroPoint) {
    return Status::kInvalidArgument;
  }

  sampling_plan_valid_ = false;
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

  if (!sampling_plan_valid_ || cached_width_ != source.width ||
      cached_height_ != source.height ||
      cached_stride_bytes_ != source.stride_bytes ||
      cached_bytes_per_pixel_ != bytes_per_pixel) {
    const Status plan_status = BuildSamplingPlan(source, bytes_per_pixel);
    if (plan_status != Status::kOk) {
      return plan_status;
    }
  }

  switch (source.format) {
    case PixelFormat::kRgb888:
      return RunRgb888(source, destination);
    case PixelFormat::kRgb565BigEndian:
      return RunRgb565(source, true, destination);
    case PixelFormat::kRgb565LittleEndian:
      return RunRgb565(source, false, destination);
    default:
      return Status::kUnsupportedPixelFormat;
  }
}

Status ImagePreprocessor::BuildSamplingPlan(
    const ImageView& source,
    const std::size_t bytes_per_pixel) noexcept {
  const std::size_t width = source.width;
  const std::size_t height = source.height;
  const std::size_t crop_size = width < height ? width : height;
  const std::size_t crop_x = (width - crop_size) / 2U;
  const std::size_t crop_y = (height - crop_size) / 2U;

  std::size_t* x_offset = x_byte_offsets_.data();
  const std::size_t* const x_end = x_offset + x_byte_offsets_.size();
  std::size_t destination_x = 0U;
  while (x_offset != x_end) {
    const std::size_t source_x =
        crop_x + (destination_x * crop_size) /
                     static_cast<std::size_t>(model_contract::kInputWidth);
    *x_offset++ = source_x * bytes_per_pixel;
    ++destination_x;
  }

  std::size_t* y_offset = y_byte_offsets_.data();
  const std::size_t* const y_end = y_offset + y_byte_offsets_.size();
  std::size_t destination_y = 0U;
  while (y_offset != y_end) {
    // Exact training mapping:
    // source_index = (destination_index * square_size) / 96.
    const std::size_t source_y =
        crop_y + (destination_y * crop_size) /
                     static_cast<std::size_t>(model_contract::kInputHeight);
    *y_offset++ = source_y * source.stride_bytes;
    ++destination_y;
  }

  cached_width_ = source.width;
  cached_height_ = source.height;
  cached_stride_bytes_ = source.stride_bytes;
  cached_bytes_per_pixel_ = static_cast<std::uint8_t>(bytes_per_pixel);
  sampling_plan_valid_ = true;
  return Status::kOk;
}

Status ImagePreprocessor::RunRgb888(const ImageView& source,
                                    std::int8_t* destination) noexcept {
  const std::size_t* const x_begin = x_byte_offsets_.data();
  const std::size_t* const x_end = x_begin + x_byte_offsets_.size();
  const std::size_t* y_offset = y_byte_offsets_.data();
  const std::size_t* const y_end = y_offset + y_byte_offsets_.size();

  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;

    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel = row + *offset++;
      *destination++ = QuantizeRgbChannel(*pixel);
      *destination++ = QuantizeRgbChannel(*(pixel + 1));
      *destination++ = QuantizeRgbChannel(*(pixel + 2));
    }
  }
  return Status::kOk;
}

Status ImagePreprocessor::RunRgb565(const ImageView& source,
                                    const bool big_endian,
                                    std::int8_t* destination) noexcept {
  const std::size_t* const x_begin = x_byte_offsets_.data();
  const std::size_t* const x_end = x_begin + x_byte_offsets_.size();
  const std::size_t* y_offset = y_byte_offsets_.data();
  const std::size_t* const y_end = y_offset + y_byte_offsets_.size();

  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;

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
      *destination++ = QuantizeRgbChannel(red);
      *destination++ = QuantizeRgbChannel(green);
      *destination++ = QuantizeRgbChannel(blue);
    }
  }
  return Status::kOk;
}

}  // namespace aiot
