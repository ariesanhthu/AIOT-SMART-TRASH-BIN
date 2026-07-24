#pragma once

// Copy this file to secrets.h and fill in your values.
// secrets.h is git-ignored and must never be committed.

// Wi-Fi credentials. Previously stored NVS credentials are tried first.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Cloudinary unsigned upload (no API_SECRET on device!)
// Create an unsigned upload preset at:
//   https://console.cloudinary.com/settings/upload
#define CLOUDINARY_CLOUD_NAME ""
#define CLOUDINARY_UPLOAD_PRESET ""

// Backend device authentication. The device exchanges DEVICE_PROVISION_SECRET
// for a short-lived device JWT (POST /api/devices/{deviceId}/auth-token),
// then uses that JWT as a bearer token against
// POST /api/devices/{deviceId}/events. Never put the backend's JWT *signing*
// secret (device.jwt.secret) here — only the provisioning secret.
#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL ""
#endif
#ifndef DEVICE_PROVISION_SECRET
#define DEVICE_PROVISION_SECRET ""
#endif

// Optional override of the device id derived from network_config::kDeviceId.
#define FIREBASE_DEVICE_ID "esp32cam-01"
