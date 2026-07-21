const { onDocumentCreated } = require("firebase-functions/v2/firestore");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore, FieldValue } = require("firebase-admin/firestore");

initializeApp();
const db = getFirestore();

const WASTE_TYPES = ["organic", "paper", "plastic"];

// daily_stats is keyed by the day the event happened on the device, not the
// day Firestore received it — see design doc §6.3 (synced_late events must
// still land in the correct day's bucket).
function toDateKey(deviceTimestamp) {
  return deviceTimestamp.toDate().toISOString().slice(0, 10);
}

// devices/{deviceId}/events/{eventId} onCreate: this is the side-effect
// layer the design doc moved out of the backend once ESP32 started writing
// events directly to Firestore (design doc §2.1/§4.2) — increments
// daily_stats and flips a compartment to "full" on FULL_ALERT.
exports.onDeviceEventCreated = onDocumentCreated(
  "devices/{deviceId}/events/{eventId}",
  async (event) => {
    const snapshot = event.data;
    if (!snapshot) {
      return;
    }

    const data = snapshot.data();
    const { deviceId } = event.params;

    if (data.event_type === "CLASSIFY" && WASTE_TYPES.includes(data.waste_type)) {
      const dateKey = toDateKey(data.device_timestamp);
      const statsRef = db.doc(`daily_stats/${deviceId}_${dateKey}`);
      await statsRef.set(
        {
          device_id: deviceId,
          date: dateKey,
          [`${data.waste_type}_count`]: FieldValue.increment(1),
          total_count: FieldValue.increment(1),
        },
        { merge: true }
      );
    }

    if (data.event_type === "FULL_ALERT" && WASTE_TYPES.includes(data.target_compartment)) {
      const deviceRef = db.doc(`devices/${deviceId}`);
      await deviceRef.update({
        [`compartments.${data.target_compartment}.status`]: "full",
      });
    }
  }
);
