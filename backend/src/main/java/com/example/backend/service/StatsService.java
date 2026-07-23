package com.example.backend.service;

import com.example.backend.dto.response.DailyStatResponse;
import com.example.backend.dto.response.DailyStatSummaryResponse;
import com.example.backend.dto.response.DeviceRankResponse;
import com.example.backend.model.DailyStat;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import com.google.cloud.firestore.QuerySnapshot;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
@Slf4j
@Service
public class StatsService {

    private final Firestore firestore;

    public StatsService(Firestore firestore) {
        this.firestore = firestore;
    }

    public List<DailyStatResponse> getDailyStats(String deviceId, String from, String to) {
        Query query = firestore.collection("daily_stats")
                .whereEqualTo("device_id", deviceId);

        if (from != null && !from.isBlank()) {
            query = query.whereGreaterThanOrEqualTo("date", from);
        }
        if (to != null && !to.isBlank()) {
            query = query.whereLessThanOrEqualTo("date", to);
        }

        query = query.orderBy("date", Query.Direction.ASCENDING);

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
                .map(this::toDailyStatResponse)
                .collect(Collectors.toList());
    }

    public DailyStatSummaryResponse getSummary(int days) {
        LocalDate today = LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"));
        String fromDate = today.minus(days - 1, ChronoUnit.DAYS).toString();
        String toDate = today.toString();

        Query query = firestore.collection("daily_stats")
                .whereGreaterThanOrEqualTo("date", fromDate)
                .whereLessThanOrEqualTo("date", toDate);

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

        long organic = 0, paper = 0, plastic = 0;
        for (QueryDocumentSnapshot doc : snapshot.getDocuments()) {
            DailyStat stat = doc.toObject(DailyStat.class);
            organic += stat.getOrganicCount() != null ? stat.getOrganicCount() : 0;
            paper += stat.getPaperCount() != null ? stat.getPaperCount() : 0;
            plastic += stat.getPlasticCount() != null ? stat.getPlasticCount() : 0;
        }

        return new DailyStatSummaryResponse(
                toDate, organic, paper, plastic, paper + plastic, organic + paper + plastic
        );
    }

    public List<DeviceRankResponse> getRanking(int days) {
        LocalDate today = LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"));
        LocalDate fromDate = today.minusDays(days - 1);
        String from = fromDate.toString();
        String to = today.toString();

        Query query = firestore.collection("daily_stats")
                .whereGreaterThanOrEqualTo("date", from)
                .whereLessThanOrEqualTo("date", to);

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
                .map(doc -> doc.toObject(DailyStat.class))
                .collect(Collectors.groupingBy(DailyStat::getDeviceId, Collectors.summingLong(stat -> stat.getTotalCount() != null ? stat.getTotalCount() : 0)))
                .entrySet().stream()
                .map(entry -> new DeviceRankResponse(entry.getKey(), entry.getValue()))
                .sorted((a, b) -> Long.compare(b.totalCount(), a.totalCount()))
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