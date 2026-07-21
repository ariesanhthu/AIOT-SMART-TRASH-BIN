package com.example.backend.dto.response;

public record DailyStatSummaryResponse(
        String date,
        long organicCount,
        long paperCount,
        long plasticCount,
        long recyclableCount,
        long totalCount
) {}