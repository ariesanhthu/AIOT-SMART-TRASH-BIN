#pragma once

#include <cstdint>

namespace aiot::network_config {

// Current IPv4 address of the computer running server-tmp on AIoTSTB.
// server-tmp prints the correct LAN endpoint when it starts. Update this value
// and rebuild if DHCP assigns the computer a different address.
inline constexpr char kServerUrl[] =
    "http://172.20.10.4:8000/api/v1/detections";

// Must match AIOT_DEVICE_TOKEN on the FastAPI server.
inline constexpr char kDeviceToken[] = "aiot-demo-token";
inline constexpr char kDeviceId[] = "esp32cam-01";

inline constexpr std::uint32_t kInitialWifiTimeoutMs = 15000;
inline constexpr std::uint32_t kReconnectTimeoutMs = 4000;
inline constexpr std::uint32_t kProvisioningTimeoutMs = 180000;
inline constexpr std::uint32_t kProvisioningCleanupTimeoutMs = 5000;
inline constexpr char kProvisioningPop[] = "bin2026";
inline constexpr std::uint32_t kHttpConnectTimeoutMs = 4000;
inline constexpr std::uint32_t kHttpResponseTimeoutMs = 7000;
inline constexpr std::uint8_t kTelemetryJpegQuality = 80;

// Camera website endpoints: GET /capture on port 80 and GET /stream on 81.
inline constexpr std::uint8_t kWebJpegQuality = 72;
inline constexpr std::uint32_t kWebCaptureTimeoutMs = 1500;
inline constexpr std::uint32_t kWebStreamFrameIntervalMs = 120;
inline constexpr std::uint32_t kWebStreamRetryDelayMs = 40;
inline constexpr char kWebStreamFramerateHeader[] = "8";
inline constexpr char kMdnsHostname[] = "esp-trash";

}  // namespace aiot::network_config
