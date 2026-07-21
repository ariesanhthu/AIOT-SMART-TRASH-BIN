package com.example.backend.dto.response;

public record DailyStatResponse(
        String deviceId,
        String date,
        long organicCount,
        long paperCount,
        long plasticCount,
        long totalCount
) {}