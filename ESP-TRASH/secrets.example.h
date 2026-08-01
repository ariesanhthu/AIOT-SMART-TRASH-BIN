#pragma once

// Copy this file to secrets.h and fill in your values.
// secrets.h is git-ignored and must never be committed.

// Wi-Fi credentials. Previously stored NVS credentials are tried first.
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Cloudinary unsigned upload. ESP uploads the JPEG here first, then stores the
// returned secure_url in Firestore. Never put an API secret on ESP32.
#define CLOUDINARY_CLOUD_NAME ""
#define CLOUDINARY_UPLOAD_PRESET ""

// Authenticate with Firebase and write directly to Firestore REST.
// The Firebase user must be allowed by firestore.rules for FIREBASE_DEVICE_ID.
#define FIREBASE_PROJECT_ID ""
#define FIREBASE_API_KEY ""
#define FIREBASE_USER_EMAIL ""
#define FIREBASE_USER_PASSWORD ""

// Shared device id for both cloud modes. If empty, network_config::kDeviceId
// is used.
#define FIREBASE_DEVICE_ID "esp32cam-01"
