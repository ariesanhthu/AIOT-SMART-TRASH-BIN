#pragma once

#include <cstdint>
#include <ctime>

namespace aiot::network_config {

inline constexpr char kDeviceId[] = "esp32cam-01";
inline constexpr char kFirmwareVersion[] = "v5.0-local-python-server";
inline constexpr char kAiModelVersion[] = "tinycnn-v9-balanced-esp-contract";

// The computer and ESP stay on Wi-Fi AIoTSTB. If that network assigns the
// computer a different IPv4 address, update both constants below.
inline constexpr char kLocalServerHost[] = "172.20.10.4";
inline constexpr std::uint16_t kLocalServerPort = 8000;
inline constexpr char kLocalServerUploadPath[] = "/api/v1/detections";
inline constexpr char kLocalServerHealthPath[] = "/health";
inline constexpr char kServerUrl[] =
    "http://172.20.10.4:8000/api/v1/detections";
inline constexpr char kDeviceToken[] = "aiot-demo-token";

inline constexpr std::uint32_t kInitialWifiTimeoutMs = 5000;
inline constexpr std::uint32_t kReconnectTimeoutMs = 4000;
inline constexpr std::uint32_t kHttpConnectTimeoutMs = 4000;
inline constexpr std::uint32_t kHttpResponseTimeoutMs = 7000;
inline constexpr std::uint32_t kCloudHttpTimeoutMs = 15000;
inline constexpr int kCloudHttpReceiveBufferBytes = 2048;
inline constexpr int kCloudHttpTransmitBufferBytes = 4096;
inline constexpr std::uint32_t kClockSyncTimeoutMs = 10000;
// Nano may hold a servo open for 5 seconds before measuring all compartments.
// Leave enough margin for sensor retries and an F packet retransmission.
inline constexpr std::uint32_t kNanoFillTimeoutMs = 30000;
inline constexpr std::uint32_t kMonitorFillTimeoutMs = 60000;
// Backend Device JWT defaults to 24 hours; renew locally after 23 hours.
inline constexpr std::uint32_t kBackendTokenRefreshMs =
    23U * 60U * 60U * 1000U;
inline constexpr std::time_t kMinimumValidEpoch = 1700000000;
inline constexpr std::uint8_t kFullThresholdPercent = 80;
inline constexpr std::uint8_t kTelemetryJpegQuality = 80;

// Give the object time to enter the camera view, then discard the framebuffer
// that CAMERA_GRAB_WHEN_EMPTY may have filled before the trigger.
inline constexpr std::uint32_t kTriggerToCaptureDelayMs = 2000;
inline constexpr std::uint8_t kFreshCaptureDiscardFrames = 1;

// Camera website endpoints: GET /capture on port 80 and GET /stream on 81.
inline constexpr std::uint8_t kWebJpegQuality = 72;
inline constexpr std::uint32_t kWebCaptureTimeoutMs = 1500;
inline constexpr std::uint32_t kWebStreamFrameIntervalMs = 120;
inline constexpr std::uint32_t kWebStreamRetryDelayMs = 40;
inline constexpr char kWebStreamFramerateHeader[] = "8";
inline constexpr char kMdnsHostname[] = "esp-trash";

}  // namespace aiot::network_config
