# Backend

Spring Boot service that talks to Firestore via the Admin SDK on behalf of the dashboard, and issues device credentials for ESP32 firmware.

## Local setup

1. Get `serviceAccountKey.json` (Firebase Console → Project settings → Service accounts → Generate new private key for project `smart-trash-bin-828c1`) and place it at `backend/secrets/serviceAccountKey.json` (gitignored, matches `firebase.credentials.path` in `application.properties`).
2. Set `DEVICE_PROVISIONING_SECRET` in your environment before starting the app — this is the shared secret ESP32 firmware presents to `/api/devices/{deviceId}/auth-token`. Left blank, that endpoint fails closed (see `DeviceAuthService`). Do not commit the real value.
3. Run `./gradlew bootRun`.

## Device-side credentials

The Admin SDK key above must never reach firmware — it bypasses Firestore Security Rules entirely. Devices instead need a Firebase **Web API key** (safe to embed) plus the `DEVICE_PROVISIONING_SECRET` above. The full flow — how firmware exchanges that secret for a Firestore-usable credential — is documented in [`docs/architecture/De_xuat_ket_noi_ESP32_Firestore.md`](../docs/architecture/De_xuat_ket_noi_ESP32_Firestore.md).
