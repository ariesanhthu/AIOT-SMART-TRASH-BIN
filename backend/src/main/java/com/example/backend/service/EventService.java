package com.example.backend.service;

import com.example.backend.dto.response.EventResponse;
import com.example.backend.model.EventData;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import com.google.cloud.firestore.QuerySnapshot;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

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
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }

        return snapshot.getDocuments().stream()
                .map(this::toEventResponse)
                .collect(Collectors.toList());
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
                event.getAiModelVersion()
        );
    }
}