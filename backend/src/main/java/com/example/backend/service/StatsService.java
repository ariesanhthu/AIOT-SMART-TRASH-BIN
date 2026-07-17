package com.example.backend.service;

import com.example.backend.dto.response.DailyStatResponse;
import com.example.backend.model.DailyStat;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import com.google.cloud.firestore.QuerySnapshot;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

@Service
public class StatsService {

    private final Firestore firestore;

    public StatsService(Firestore firestore) {
        this.firestore = firestore;
    }

    public List<DailyStatResponse> getDailyStats(String deviceId, String from, String to) {
        Query query = firestore.collection("daily_stats")
                .whereEqualTo("device_id", deviceId)
                .whereGreaterThanOrEqualTo("date", from)
                .whereLessThanOrEqualTo("date", to)
                .orderBy("date", Query.Direction.ASCENDING);

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
                .map(this::toDailyStatResponse)
                .collect(Collectors.toList());
    }

    private DailyStatResponse toDailyStatResponse(QueryDocumentSnapshot doc) {
        DailyStat stat = doc.toObject(DailyStat.class);

        return new DailyStatResponse(
                stat.getDeviceId(),
                stat.getDate(),
                stat.getOrganicCount() != null ? stat.getOrganicCount() : 0,
                stat.getPaperCount() != null ? stat.getPaperCount() : 0,
                stat.getPlasticCount() != null ? stat.getPlasticCount() : 0,
                stat.getTotalCount() != null ? stat.getTotalCount() : 0
        );
    }
}