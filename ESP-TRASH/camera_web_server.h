#pragma once

#include "camera_adapter.h"

namespace aiot {

// Starts a snapshot server on port 80 and an MJPEG server on port 81.
// Safe to call more than once; already-running servers are left untouched.
[[nodiscard]] bool StartCameraWebServer(CameraAdapter* camera) noexcept;

}  // namespace aiot
