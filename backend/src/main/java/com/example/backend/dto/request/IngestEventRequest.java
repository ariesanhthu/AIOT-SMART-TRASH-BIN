package com.example.backend.dto.request;

import java.util.Map;

/**
 * Request body sent by ESP32 firmware when posting a classification or alert
 * event to POST /api/devices/{deviceId}/events.
 *
 * Field names match the ESP32 JSON payload structure in cloud_sync.cpp.
 * The Backend writes these fields verbatim into Firestore using Admin SDK.
 */
public record IngestEventRequest(
        /** "CLASSIFY" | "FULL_ALERT" | "ERROR" | "MAINTENANCE" */
        String eventType,

        /** "organic" | "paper" | "plastic" | null */
        String wasteType,

        String targetCompartment,

        Double aiConfidence,

        /** Keys: "organic", "paper", "plastic" — values: fill percentage 0-100 */
        Map<String, Double> fillPercent,

        Double alertThreshold,

        /** ISO-8601 UTC string from firmware, e.g. "2026-07-24T12:00:00Z" */
        String deviceTimestamp,

        Boolean syncedLate,

        String firmwareVersion,

        String aiModelVersion,

        /** Cloudinary secure_url uploaded by firmware before calling this endpoint */
        String imageUrl
) {}
