#pragma once

#include <cstdint>

namespace aiot {

enum class Status : std::uint8_t {
  kOk = 0,
  kInvalidArgument,
  kNotInitialized,
  kAlreadyInitialized,
  kPsramUnavailable,
  kCameraInitFailed,
  kCameraBusy,
  kCameraCaptureFailed,
  kUnsupportedPixelFormat,
  kInvalidImageBuffer,
  kInvalidModel,
  kModelSchemaMismatch,
  kOperatorRegistrationFailed,
  kTensorAllocationFailed,
  kTensorContractMismatch,
  kModelSelfTestFailed,
  kPreprocessFailed,
  kInvokeFailed,
  kPostprocessFailed,
};

[[nodiscard]] const char* StatusName(Status status) noexcept;

}  // namespace aiot
