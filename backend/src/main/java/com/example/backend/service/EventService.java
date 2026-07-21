package com.example.backend.service;

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

import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class EventService {

    private final Firestore firestore;

    public EventService(Firestore firestore) {
        this.firestore = firestore;
    }

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
                    "resolved_at", Timestamp.now(),
                    "resolved_by", resolvedByEmail != null ? resolvedByEmail : "unknown"
            )).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bi gian doan khi cap nhat alert", e);
        } catch (ExecutionException e) {
            log.error("Loi khi cap nhat alert", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
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
                event.getReceivedAt() != null ? event.getReceivedAt().toDate().toInstant().toString() : null,
                Boolean.TRUE.equals(event.getSyncedLate()),
                event.getFirmwareVersion(),
                event.getAiModelVersion(),
                event.getAlertStatus(),
                event.getResolvedAt() != null ? event.getResolvedAt().toDate().toInstant().toString() : null,
                event.getResolvedBy(),
                event.getImageUrl()
        );
    }
}
