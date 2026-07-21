#pragma once

#include <cstddef>
#include <cstdint>

namespace aiot
{
  struct CompartmentFillLevels
  {
    std::uint8_t plastic = 0;
    std::uint8_t paper = 0;
    std::uint8_t organic = 0;
    bool received = false;
  };

  struct CloudRecognition
  {
    const std::uint8_t *jpeg_data = nullptr;
    std::size_t jpeg_length = 0;
    const char *waste_type = nullptr;
    float confidence = 0.0F;
    bool has_classification = false;
  };

  // Synchronizes UTC for TLS verification and Firestore timestamp fields.
  bool InitializeCloudClock();

  // Uploads the JPEG to Cloudinary, then updates the Firestore device and
  // appends one CLASSIFY/ERROR event containing the resulting image URL.
  bool SyncRecognitionToCloud(const CloudRecognition &recognition,
                              const CompartmentFillLevels &fill_levels);
} // namespace aiot
