package com.example.backend.service;

import com.google.cloud.firestore.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import com.google.cloud.Timestamp;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;

@Slf4j
@Component
public class DailyStatsAggregationJob {

    private static final List<String> WASTE_TYPES = List.of("organic", "paper", "plastic");
    private static final String CHECKPOINT_DOC = "daily_stats_aggregator";

    private final Firestore firestore;

    public DailyStatsAggregationJob(Firestore firestore) {
        this.firestore = firestore;
    }

    @Scheduled(fixedRate = 60000) // 60s — chỉnh lại nếu cần sát real-time hơn
    public void aggregate() {
        try {
            Timestamp lastProcessed = getCheckpoint();

            CollectionGroup eventsGroup = firestore.collectionGroup("events");
            Query query = eventsGroup
                    .whereEqualTo("event_type", "CLASSIFY")
                    .whereGreaterThan("received_at", lastProcessed)
                    .orderBy("received_at", Query.Direction.ASCENDING);

            QuerySnapshot snapshot = query.get().get();
            List<QueryDocumentSnapshot> docs = snapshot.getDocuments();
            if (docs.isEmpty()) {
                return;
            }

            Timestamp newCheckpoint = lastProcessed;

            for (QueryDocumentSnapshot doc : docs) {
                String wasteType = doc.getString("waste_type");
                Timestamp deviceTimestamp = doc.getTimestamp("device_timestamp");
                String deviceId = doc.getReference().getParent().getParent().getId();

                if (wasteType != null && WASTE_TYPES.contains(wasteType) && deviceTimestamp != null) {
                    incrementDailyStat(deviceId, deviceTimestamp, wasteType);
                }

                Timestamp receivedAt = doc.getTimestamp("received_at");
                if (receivedAt != null && receivedAt.compareTo(newCheckpoint) > 0) {
                    newCheckpoint = receivedAt;
                }
            }

            setCheckpoint(newCheckpoint);
            log.info("Đã aggregate {} event CLASSIFY, checkpoint mới: {}", docs.size(), newCheckpoint);

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("Bị gián đoạn khi aggregate daily_stats", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi aggregate daily_stats", e.getCause());
        }
    }

    private void incrementDailyStat(String deviceId, Timestamp deviceTimestamp, String wasteType)
            throws ExecutionException, InterruptedException {
        String dateKey = LocalDate.ofInstant(deviceTimestamp.toDate().toInstant(), ZoneOffset.UTC).toString();

        DocumentReference statsRef = firestore.collection("daily_stats")
                .document(deviceId + "_" + dateKey);

        Map<String, Object> update = new HashMap<>();
        update.put("device_id", deviceId);
        update.put("date", dateKey);
        update.put(wasteType + "_count", FieldValue.increment(1));
        update.put("total_count", FieldValue.increment(1));

        statsRef.set(update, SetOptions.merge()).get();
    }

    private Timestamp getCheckpoint() throws ExecutionException, InterruptedException {
        DocumentSnapshot snap = firestore.collection("job_state").document(CHECKPOINT_DOC).get().get();
        return snap.exists() && snap.getTimestamp("last_processed_at") != null
                ? snap.getTimestamp("last_processed_at")
                : Timestamp.ofTimeSecondsAndNanos(0, 0);
    }

    private void setCheckpoint(Timestamp ts) throws ExecutionException, InterruptedException {
        firestore.collection("job_state").document(CHECKPOINT_DOC)
                .set(Map.of("last_processed_at", ts)).get();
    }
}