package com.example.backend.dto.request;

import java.util.Map;

/**
 * Body cho PATCH /api/devices/{id}/config.
 * Chỉ field nào có mặt (khác null) mới được ghi xuống Firestore.
 * thresholds: key là "organic" | "paper" | "plastic", value là ngưỡng 0.0 - 1.0
 */
public record UpdateDeviceConfigRequest(
        Map<String, Double> thresholds,
        Boolean maintenanceMode
) {}