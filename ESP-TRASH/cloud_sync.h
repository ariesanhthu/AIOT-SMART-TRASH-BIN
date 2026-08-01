#pragma once

#include <cstddef>
#include <cstdint>

#include <WString.h>

namespace aiot
{
  struct CompartmentFillLevels
  {
    std::uint8_t plastic = 0;
    std::uint8_t paper = 0;
    std::uint8_t organic = 0;
    bool received = false;
  };

  // Per-compartment "already alerted" latch, owned by the caller (firmware.cpp)
  // and passed into SendFullAlertsIfNeeded() to debounce repeated FULL_ALERT
  // events while a compartment stays over threshold.
  struct CompartmentAlertState
  {
    bool organic_alerted = false;
    bool paper_alerted = false;
    bool plastic_alerted = false;
  };

  struct CloudRecognition
  {
    const std::uint8_t *jpeg_data = nullptr;
    std::size_t jpeg_length = 0;
    const char *waste_type = nullptr;
    float confidence = 0.0F;
    bool has_classification = false;
  };

  // Synchronizes UTC for TLS verification and Firestore timestamps.
  bool InitializeCloudClock();

  // Authenticates Firebase before uploading the JPEG.
  bool PrepareCloudSync();

  // Uploads the JPEG to Cloudinary (if configured) and returns the resulting
  // secure_url, or an empty string if upload was skipped/failed.
  String UploadRecognitionImage(const CloudRecognition &recognition);

  // Writes one CLASSIFY/ERROR event directly to Firestore.
  bool SyncRecognitionToCloud(const CloudRecognition &recognition,
                              const CompartmentFillLevels &fill_levels,
                              const String &image_url);

  // Compares fill_levels against network_config::kFullThresholdPercent per
  // compartment; posts one FULL_ALERT event per compartment that just crossed
  // the threshold (and isn't already latched in alert_state), and clears the
  // latch for compartments that have dropped back below threshold so a future
  // crossing re-alerts. Returns the number of FULL_ALERT events sent
  // successfully (may legitimately be 0).
  int SendFullAlertsIfNeeded(const CompartmentFillLevels &fill_levels,
                             CompartmentAlertState *alert_state,
                             const char *image_url);
} // namespace aiot
