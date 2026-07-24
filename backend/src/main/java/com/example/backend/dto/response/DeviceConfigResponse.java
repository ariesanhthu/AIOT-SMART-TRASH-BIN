package com.example.backend.dto.response;

import java.util.Map;

/**
 * Returned by GET /api/devices/{deviceId}/config.
 *
 * ESP32 firmware calls this endpoint to pull its operational configuration
 * (thresholds and maintenance mode) from Firestore via the Backend API.
 * This replaces the direct Firestore read the firmware previously performed.
 */
public record DeviceConfigResponse(
        String deviceId,
        Boolean maintenanceMode,
        /** Keys: "organic", "paper", "plastic" — values: fill threshold (0.0–1.0 or 0–100) */
        Map<String, Double> thresholds
) {}
