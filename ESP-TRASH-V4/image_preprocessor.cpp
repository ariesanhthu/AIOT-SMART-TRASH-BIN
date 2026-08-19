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
constexpr std::uint16_t kUnityGainQ8 = 256U;
constexpr std::uint16_t kMinimumGainQ8 = 192U;
constexpr std::uint16_t kMaximumGainQ8 = 341U;
constexpr std::uint8_t kMinimumMeanLuma = 96U;
constexpr std::uint8_t kMaximumMeanLuma = 160U;
constexpr std::uint16_t kUnityWhiteBalanceGainQ10 = 1024U;
constexpr std::uint16_t kMinimumWhiteBalanceGainQ10 = 768U;
constexpr std::uint16_t kMaximumWhiteBalanceGainQ10 = 1365U;

struct RgbPixel final {
  std::uint8_t red;
  std::uint8_t green;
  std::uint8_t blue;
};

struct WhiteBalanceGains final {
  std::uint16_t red_q10;
  std::uint16_t green_q10;
  std::uint16_t blue_q10;
};

[[nodiscard]] constexpr RgbPixel TruncateToRgb565(
    const RgbPixel pixel) noexcept {
  return {
      static_cast<std::uint8_t>((pixel.red / 8U) * 8U),
      static_cast<std::uint8_t>((pixel.green / 4U) * 4U),
      static_cast<std::uint8_t>((pixel.blue / 8U) * 8U),
  };
}

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

[[nodiscard]] constexpr RgbPixel DecodeRgb565(
    const std::uint8_t* const bytes, const bool big_endian) noexcept {
  const std::uint16_t packed =
      big_endian
          ? static_cast<std::uint16_t>((bytes[0] << 8U) | bytes[1])
          : static_cast<std::uint16_t>((bytes[1] << 8U) | bytes[0]);
  return {
      Expand5To8((packed >> 11U) & 0x1FU),
      Expand6To8((packed >> 5U) & 0x3FU),
      Expand5To8(packed & 0x1FU),
  };
}

[[nodiscard]] constexpr std::uint8_t Luminance(
    const RgbPixel pixel) noexcept {
  return static_cast<std::uint8_t>(
      (77U * pixel.red + 150U * pixel.green + 29U * pixel.blue + 128U) >>
      8U);
}

[[nodiscard]] constexpr std::uint8_t ApplyGain(
    const std::uint8_t value, const std::uint16_t gain_q8) noexcept {
  const std::uint32_t scaled =
      (static_cast<std::uint32_t>(value) * gain_q8 + 128U) >> 8U;
  return static_cast<std::uint8_t>(scaled > 255U ? 255U : scaled);
}

[[nodiscard]] constexpr std::uint8_t ApplyWhiteBalanceGain(
    const std::uint8_t value, const std::uint16_t gain_q10) noexcept {
  const std::uint32_t scaled =
      (static_cast<std::uint32_t>(value) * gain_q10 + 512U) >> 10U;
  return static_cast<std::uint8_t>(scaled > 255U ? 255U : scaled);
}

[[nodiscard]] constexpr RgbPixel ApplyWhiteBalance(
    const RgbPixel pixel, const WhiteBalanceGains gains) noexcept {
  return {
      ApplyWhiteBalanceGain(pixel.red, gains.red_q10),
      ApplyWhiteBalanceGain(pixel.green, gains.green_q10),
      ApplyWhiteBalanceGain(pixel.blue, gains.blue_q10),
  };
}

[[nodiscard]] WhiteBalanceGains GainsFromChannelSums(
    const std::uint32_t red_sum, const std::uint32_t green_sum,
    const std::uint32_t blue_sum) noexcept {
  constexpr std::uint32_t kPixelCount =
      static_cast<std::uint32_t>(model_contract::kInputHeight) *
      static_cast<std::uint32_t>(model_contract::kInputWidth);
  const std::uint32_t red_mean = (red_sum + kPixelCount / 2U) / kPixelCount;
  const std::uint32_t green_mean =
      (green_sum + kPixelCount / 2U) / kPixelCount;
  const std::uint32_t blue_mean = (blue_sum + kPixelCount / 2U) / kPixelCount;
  const std::uint32_t target = (red_mean + green_mean + blue_mean + 1U) / 3U;

  const auto channel_gain = [target](const std::uint32_t mean) {
    const std::uint32_t safe_mean = mean == 0U ? 1U : mean;
    std::uint32_t gain =
        (target * kUnityWhiteBalanceGainQ10 + safe_mean / 2U) / safe_mean;
    if (gain < kMinimumWhiteBalanceGainQ10) {
      gain = kMinimumWhiteBalanceGainQ10;
    } else if (gain > kMaximumWhiteBalanceGainQ10) {
      gain = kMaximumWhiteBalanceGainQ10;
    }
    return static_cast<std::uint16_t>(gain);
  };
  return {channel_gain(red_mean), channel_gain(green_mean),
          channel_gain(blue_mean)};
}

[[nodiscard]] std::uint16_t GainFromLuminanceSum(
    const std::uint32_t luminance_sum) noexcept {
  constexpr std::uint32_t kPixelCount =
      static_cast<std::uint32_t>(model_contract::kInputHeight) *
      static_cast<std::uint32_t>(model_contract::kInputWidth);
  const std::uint16_t mean = static_cast<std::uint16_t>(
      (luminance_sum + kPixelCount / 2U) / kPixelCount);
  if (mean >= kMinimumMeanLuma && mean <= kMaximumMeanLuma) {
    return kUnityGainQ8;
  }
  const std::uint16_t safe_mean = mean == 0U ? 1U : mean;
  const std::uint16_t target =
      mean < kMinimumMeanLuma ? kMinimumMeanLuma : kMaximumMeanLuma;
  std::uint16_t gain = static_cast<std::uint16_t>(
      (static_cast<std::uint32_t>(target) * kUnityGainQ8 + safe_mean / 2U) /
      safe_mean);
  if (gain < kMinimumGainQ8) {
    gain = kMinimumGainQ8;
  } else if (gain > kMaximumGainQ8) {
    gain = kMaximumGainQ8;
  }
  return gain;
}

[[nodiscard]] constexpr std::int8_t QuantizeRgbChannel(
    const std::uint8_t value) noexcept {
  // The V10 input contract is q = round((pixel / 255) / (1 / 255)) - 128.
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

  std::size_t* x_offset = x_byte_offsets_.data();
  const std::size_t* const x_end = x_offset + x_byte_offsets_.size();
  std::size_t destination_x = 0U;
  while (x_offset != x_end) {
    const std::size_t source_x =
        (destination_x * width) /
        static_cast<std::size_t>(model_contract::kInputWidth);
    *x_offset++ = source_x * bytes_per_pixel;
    ++destination_x;
  }

  std::size_t* y_offset = y_byte_offsets_.data();
  const std::size_t* const y_end = y_offset + y_byte_offsets_.size();
  std::size_t destination_y = 0U;
  while (y_offset != y_end) {
    // Resize the complete frame. Cropping here would make edge inference see
    // different content from the image captured and uploaded by the ESP.
    const std::size_t source_y =
        (destination_y * height) /
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

  std::uint32_t red_sum = 0U;
  std::uint32_t green_sum = 0U;
  std::uint32_t blue_sum = 0U;
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel = row + *offset++;
      const RgbPixel rgb =
          TruncateToRgb565({pixel[0], pixel[1], pixel[2]});
      red_sum += rgb.red;
      green_sum += rgb.green;
      blue_sum += rgb.blue;
    }
  }
  const WhiteBalanceGains white_balance =
      GainsFromChannelSums(red_sum, green_sum, blue_sum);

  std::uint32_t luminance_sum = 0U;
  y_offset = y_byte_offsets_.data();
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel = row + *offset++;
      const RgbPixel rgb = ApplyWhiteBalance(
          TruncateToRgb565({pixel[0], pixel[1], pixel[2]}), white_balance);
      luminance_sum += Luminance(rgb);
    }
  }
  const std::uint16_t gain_q8 = GainFromLuminanceSum(luminance_sum);

  y_offset = y_byte_offsets_.data();
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel = row + *offset++;
      const RgbPixel rgb = ApplyWhiteBalance(
          TruncateToRgb565({pixel[0], pixel[1], pixel[2]}), white_balance);
      *destination++ = QuantizeRgbChannel(ApplyGain(rgb.red, gain_q8));
      *destination++ = QuantizeRgbChannel(ApplyGain(rgb.green, gain_q8));
      *destination++ = QuantizeRgbChannel(ApplyGain(rgb.blue, gain_q8));
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

  std::uint32_t red_sum = 0U;
  std::uint32_t green_sum = 0U;
  std::uint32_t blue_sum = 0U;
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const std::uint8_t* const pixel_bytes = row + *offset++;
      const RgbPixel rgb = DecodeRgb565(pixel_bytes, big_endian);
      red_sum += rgb.red;
      green_sum += rgb.green;
      blue_sum += rgb.blue;
    }
  }
  const WhiteBalanceGains white_balance =
      GainsFromChannelSums(red_sum, green_sum, blue_sum);

  std::uint32_t luminance_sum = 0U;
  y_offset = y_byte_offsets_.data();
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const RgbPixel pixel = ApplyWhiteBalance(
          DecodeRgb565(row + *offset++, big_endian), white_balance);
      luminance_sum += Luminance(pixel);
    }
  }
  const std::uint16_t gain_q8 = GainFromLuminanceSum(luminance_sum);

  y_offset = y_byte_offsets_.data();
  while (y_offset != y_end) {
    const std::uint8_t* const row = source.data + *y_offset++;
    const std::size_t* offset = x_begin;
    while (offset != x_end) {
      const RgbPixel pixel = ApplyWhiteBalance(
          DecodeRgb565(row + *offset++, big_endian), white_balance);
      *destination++ = QuantizeRgbChannel(ApplyGain(pixel.red, gain_q8));
      *destination++ = QuantizeRgbChannel(ApplyGain(pixel.green, gain_q8));
      *destination++ = QuantizeRgbChannel(ApplyGain(pixel.blue, gain_q8));
    }
  }
  return Status::kOk;
}

}  // namespace aiot
