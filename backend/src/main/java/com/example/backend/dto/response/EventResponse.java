package com.example.backend.dto.response;

import java.util.Map;

public record EventResponse(
        String id,
        String eventType,
        String wasteType,
        String targetCompartment,
        Double aiConfidence,
        Map<String, Double> fillPercent,
        Double alertThreshold,
        String deviceTimestamp,
        String receivedAt,
        boolean syncedLate,
        String firmwareVersion,
        String aiModelVersion,
        String alertStatus,
        String resolvedAt,
        String resolvedBy,
        String imageUrl
) {}
