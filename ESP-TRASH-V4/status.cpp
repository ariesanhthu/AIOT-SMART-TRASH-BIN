#include "status.h"

namespace aiot {

const char* StatusName(const Status status) noexcept {
  switch (status) {
    case Status::kOk:
      return "ok";
    case Status::kInvalidArgument:
      return "invalid_argument";
    case Status::kNotInitialized:
      return "not_initialized";
    case Status::kAlreadyInitialized:
      return "already_initialized";
    case Status::kPsramUnavailable:
      return "psram_unavailable";
    case Status::kCameraInitFailed:
      return "camera_init_failed";
    case Status::kCameraBusy:
      return "camera_busy";
    case Status::kCameraCaptureFailed:
      return "camera_capture_failed";
    case Status::kUnsupportedPixelFormat:
      return "unsupported_pixel_format";
    case Status::kInvalidImageBuffer:
      return "invalid_image_buffer";
    case Status::kInvalidModel:
      return "invalid_model";
    case Status::kModelSchemaMismatch:
      return "model_schema_mismatch";
    case Status::kOperatorRegistrationFailed:
      return "operator_registration_failed";
    case Status::kTensorAllocationFailed:
      return "tensor_allocation_failed";
    case Status::kTensorContractMismatch:
      return "tensor_contract_mismatch";
    case Status::kModelSelfTestFailed:
      return "model_self_test_failed";
    case Status::kPreprocessFailed:
      return "preprocess_failed";
    case Status::kInvokeFailed:
      return "invoke_failed";
    case Status::kPostprocessFailed:
      return "postprocess_failed";
  }
  return "unknown_status";
}

}  // namespace aiot
