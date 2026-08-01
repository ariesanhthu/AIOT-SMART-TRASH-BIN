package com.example.backend.service;

import com.example.backend.dto.request.IngestEventRequest;
import com.example.backend.dto.response.EventResponse;
import com.example.backend.model.EventData;
import com.google.cloud.Timestamp;
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import com.google.cloud.firestore.QuerySnapshot;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class EventService {

    private static final ZoneId LOCAL_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");

    private final Firestore firestore;

    public EventService(Firestore firestore) {
        this.firestore = firestore;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // ESP32 → Backend: ingest event and write to Firestore via Admin SDK
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Receives an event POSTed by ESP32 firmware, validates it, writes it to
     * Firestore (devices/{deviceId}/events/{eventId}) using the Admin SDK, and
     * side-effects the device document (last_seen_at, fill levels, status) and
     * the daily_stats aggregate document (for CLASSIFY events).
     *
     * This replaces the direct Firestore write that the firmware previously
     * performed via documents:commit. The Backend now acts as the intermediary
     * as required by the architecture diagram.
     */
    public EventResponse ingestEvent(String deviceId, IngestEventRequest req) {
        String eventId  = "evt_" + UUID.randomUUID().toString().replace("-", "");
        Timestamp deviceTs  = parseTimestamp(req.deviceTimestamp());
        Timestamp receivedAt = Timestamp.now();

        // ── 1. Build the Firestore event document ────────────────────────────
        Map<String, Object> eventDoc = new HashMap<>();
        eventDoc.put("event_type",         req.eventType());
        eventDoc.put("waste_type",         req.wasteType());
        eventDoc.put("target_compartment", req.targetCompartment());
        eventDoc.put("ai_confidence",      req.aiConfidence());
        eventDoc.put("fill_percent",       req.fillPercent() != null ? req.fillPercent() : Map.of());
        eventDoc.put("alert_threshold",    req.alertThreshold());
        eventDoc.put("device_timestamp",   deviceTs);
        eventDoc.put("received_at",        receivedAt);
        eventDoc.put("synced_late",        Boolean.TRUE.equals(req.syncedLate()));
        eventDoc.put("firmware_version",   req.firmwareVersion());
        eventDoc.put("ai_model_version",   req.aiModelVersion());
        eventDoc.put("alert_status",       "FULL_ALERT".equals(req.eventType()) ? "active" : null);
        eventDoc.put("resolved_at",        null);
        eventDoc.put("resolved_by",        null);
        eventDoc.put("image_url",          req.imageUrl());

        // ── 2. Write event document ──────────────────────────────────────────
        try {
            firestore.collection("devices").document(deviceId)
                     .collection("events").document(eventId)
                     .set(eventDoc).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Interrupted writing event to Firestore", e);
        } catch (ExecutionException e) {
            log.error("Failed to write event to Firestore", e.getCause());
            throw new RuntimeException("Failed to write event to Firestore", e.getCause());
        }

        // ── 3. Side-effect: update device document ───────────────────────────
        Map<String, Object> deviceUpdate = new HashMap<>();
        deviceUpdate.put("last_seen_at", receivedAt);
        if (req.firmwareVersion() != null) deviceUpdate.put("firmware_version", req.firmwareVersion());
        if (req.aiModelVersion()  != null) deviceUpdate.put("ai_model_version",  req.aiModelVersion());
        if (req.wasteType()       != null) deviceUpdate.put("class_name",         req.wasteType());

        if (req.fillPercent() != null) {
            req.fillPercent().forEach((type, pct) -> {
                deviceUpdate.put("compartments." + type + ".fill_percent", pct);
                // Update status: full when fill >= threshold, else normal
                boolean isFull = req.alertThreshold() != null && pct >= req.alertThreshold();
                deviceUpdate.put("compartments." + type + ".status", isFull ? "full" : "normal");
            });
        }

        try {
            firestore.collection("devices").document(deviceId).update(deviceUpdate).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("Interrupted updating device document for {}", deviceId, e);
        } catch (ExecutionException e) {
            // Non-fatal: event is already saved; log and continue
            log.warn("Failed to update device document for {} after event ingest", deviceId, e.getCause());
        }

        // ── 3.5. Side-effect: upsert daily_stats aggregate (CLASSIFY only) ────
        if ("CLASSIFY".equals(req.eventType()) && req.wasteType() != null) {
            upsertDailyStat(deviceId, req.wasteType(), receivedAt);
        }

        // ── 4. Return response ───────────────────────────────────────────────
        return new EventResponse(
                eventId,
                req.eventType(),
                req.wasteType(),
                req.targetCompartment(),
                req.aiConfidence(),
                req.fillPercent(),
                req.alertThreshold(),
                deviceTs.toDate().toInstant().toString(),
                receivedAt.toDate().toInstant().toString(),
                Boolean.TRUE.equals(req.syncedLate()),
                req.firmwareVersion(),
                req.aiModelVersion(),
                "FULL_ALERT".equals(req.eventType()) ? "active" : null,
                null,
                null,
                req.imageUrl()
        );
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Dashboard: read events from Firestore (unchanged)
    // ─────────────────────────────────────────────────────────────────────────

    public List<EventResponse> getEvents(String deviceId, String eventType, int limit) {
        Query query = firestore.collection("devices").document(deviceId).collection("events")
                .orderBy("device_timestamp", Query.Direction.DESCENDING)
                .limit(limit);

        if (eventType != null && !eventType.isBlank()) {
            query = query.whereEqualTo("event_type", eventType);
        }

        QuerySnapshot snapshot;
        try {
            snapshot = query.get().get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bị gián đoạn khi đọc Firestore", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi đọc Firestore", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }

        return snapshot.getDocuments().stream()
                .map(this::toEventResponse)
                .collect(Collectors.toList());
    }

    public void resolveAlert(String deviceId, String eventId, String resolvedByEmail) {
        DocumentReference eventRef = firestore.collection("devices").document(deviceId)
                .collection("events").document(eventId);

        try {
            DocumentSnapshot snapshot = eventRef.get().get();
            if (!snapshot.exists()) {
                throw new RuntimeException("Khong tim thay alert/event " + eventId);
            }

            EventData event = snapshot.toObject(EventData.class);
            if (event == null || !"FULL_ALERT".equals(event.getEventType())) {
                throw new RuntimeException("Event khong phai FULL_ALERT");
            }

            eventRef.update(Map.of(
                    "alert_status", "resolved",
                    "resolved_at",  Timestamp.now(),
                    "resolved_by",  resolvedByEmail != null ? resolvedByEmail : "unknown"
            )).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bi gian doan khi cap nhat alert", e);
        } catch (ExecutionException e) {
            log.error("Loi khi cap nhat alert", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Private helpers
    // ─────────────────────────────────────────────────────────────────────────

    private Timestamp parseTimestamp(String iso8601) {
        if (iso8601 == null || iso8601.isBlank()) {
            return Timestamp.now();
        }
        try {
            Instant instant = Instant.parse(iso8601);
            return Timestamp.ofTimeSecondsAndNanos(instant.getEpochSecond(), instant.getNano());
        } catch (Exception e) {
            log.warn("Cannot parse deviceTimestamp '{}', falling back to now()", iso8601);
            return Timestamp.now();
        }
    }

    /**
     * Upserts the daily_stats/{deviceId}_{yyyy-MM-dd} aggregate document,
     * incrementing the counter for the given wasteType. Uses a transaction to
     * avoid lost updates when multiple CLASSIFY events for the same device
     * land in the same day close together.
     *
     * The date bucket is computed in Asia/Ho_Chi_Minh local time (not UTC) so
     * that late-night events aren't misfiled into the previous day's stats.
     */
    private void upsertDailyStat(String deviceId, String wasteType, Timestamp receivedAt) {
        LocalDate date = receivedAt.toDate().toInstant()
                .atZone(LOCAL_ZONE)
                .toLocalDate();
        String docId = deviceId + "_" + date; // e.g. STBIN_HCMUS_001_2026-08-01

        DocumentReference ref = firestore.collection("daily_stats").document(docId);

        try {
            firestore.runTransaction(tx -> {
                DocumentSnapshot snap = tx.get(ref).get();

                long organic = snap.exists() ? Optional.ofNullable(snap.getLong("organic_count")).orElse(0L) : 0L;
                long paper   = snap.exists() ? Optional.ofNullable(snap.getLong("paper_count")).orElse(0L)   : 0L;
                long plastic = snap.exists() ? Optional.ofNullable(snap.getLong("plastic_count")).orElse(0L) : 0L;

                switch (wasteType.toLowerCase()) {
                    case "organic" -> organic++;
                    case "paper"   -> paper++;
                    case "plastic" -> plastic++;
                    default -> log.warn("Unknown wasteType '{}' when upserting daily stat for {}", wasteType, deviceId);
                }
                long total = organic + paper + plastic;

                Map<String, Object> data = new HashMap<>();
                data.put("date",          date.toString());
                data.put("device_id",     deviceId);
                data.put("organic_count", organic);
                data.put("paper_count",   paper);
                data.put("plastic_count", plastic);
                data.put("total_count",   total);

                tx.set(ref, data);
                return null;
            }).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("Interrupted upserting daily stat for {}", deviceId, e);
        } catch (ExecutionException e) {
            // Non-fatal: event is already saved; log and continue
            log.warn("Failed to upsert daily stat for {} after event ingest", deviceId, e.getCause());
        }
    }

    private EventResponse toEventResponse(QueryDocumentSnapshot doc) {
        EventData event = doc.toObject(EventData.class);

        return new EventResponse(
                doc.getId(),
                event.getEventType(),
                event.getWasteType(),
                event.getTargetCompartment(),
                event.getAiConfidence(),
                event.getFillPercent(),
                event.getAlertThreshold(),
                event.getDeviceTimestamp() != null ? event.getDeviceTimestamp().toDate().toInstant().toString() : null,
                event.getReceivedAt()      != null ? event.getReceivedAt().toDate().toInstant().toString()      : null,
                Boolean.TRUE.equals(event.getSyncedLate()),
                event.getFirmwareVersion(),
                event.getAiModelVersion(),
                event.getAlertStatus(),
                event.getResolvedAt()      != null ? event.getResolvedAt().toDate().toInstant().toString()      : null,
                event.getResolvedBy(),
                event.getImageUrl()
        );
    }
}