#pragma once

#include <cstdint>
#include <ctime>

namespace aiot::network_config {

inline constexpr char kDeviceId[] = "esp32cam-01";
inline constexpr char kFirmwareVersion[] = "v4.0-arduino";
inline constexpr char kAiModelVersion[] = "waste_v4_int8";

inline constexpr std::uint32_t kInitialWifiTimeoutMs = 15000;
inline constexpr std::uint32_t kReconnectTimeoutMs = 4000;
inline constexpr std::uint32_t kHttpConnectTimeoutMs = 4000;
inline constexpr std::uint32_t kHttpResponseTimeoutMs = 7000;
inline constexpr std::uint32_t kCloudHttpTimeoutMs = 15000;
inline constexpr int kCloudHttpReceiveBufferBytes = 2048;
inline constexpr int kCloudHttpTransmitBufferBytes = 4096;
inline constexpr std::uint32_t kClockSyncTimeoutMs = 10000;
inline constexpr std::uint32_t kNanoFillTimeoutMs = 15000;
inline constexpr std::uint32_t kMonitorFillTimeoutMs = 60000;
inline constexpr std::uint32_t kDeviceTokenRefreshMs = 55U * 60U * 1000U;
inline constexpr std::time_t kMinimumValidEpoch = 1700000000;
inline constexpr std::uint8_t kFullThresholdPercent = 80;
inline constexpr std::uint8_t kTelemetryJpegQuality = 80;

// Camera website endpoints: GET /capture on port 80 and GET /stream on 81.
inline constexpr std::uint8_t kWebJpegQuality = 72;
inline constexpr std::uint32_t kWebCaptureTimeoutMs = 1500;
inline constexpr std::uint32_t kWebStreamFrameIntervalMs = 120;
inline constexpr std::uint32_t kWebStreamRetryDelayMs = 40;
inline constexpr char kWebStreamFramerateHeader[] = "8";
inline constexpr char kMdnsHostname[] = "esp-trash";

}  // namespace aiot::network_config
