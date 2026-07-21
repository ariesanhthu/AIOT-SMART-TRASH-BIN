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

// Firebase device authentication and direct Firestore REST access.
#ifndef FIREBASE_PROJECT_ID
#define FIREBASE_PROJECT_ID "smart-trash-bin-828c1"
#endif
#ifndef FIREBASE_API_KEY
#define FIREBASE_API_KEY ""
#endif
#ifndef FIREBASE_DATABASE_URL
#define FIREBASE_DATABASE_URL "" // Realtime DB only; Firestore does not use it.
#endif
#ifndef BACKEND_BASE_URL
#define BACKEND_BASE_URL ""
#endif
#ifndef PROVISION_SECRET
#define PROVISION_SECRET ""
#endif

// Prototype fallback when the Firebase user already has a device_id custom
// claim matching FIREBASE_DEVICE_ID. Prefer backend custom-token auth above.
#define FIREBASE_USER_EMAIL ""
#define FIREBASE_USER_PASSWORD ""
#define FIREBASE_DEVICE_ID "esp32cam-01"
