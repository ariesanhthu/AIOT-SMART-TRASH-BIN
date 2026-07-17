package com.example.backend.dto.response;

import com.example.backend.model.Compartment;

import java.util.Map;

public record DeviceResponse(
        String deviceId,
        String name,
        String location,
        String lastSeenAt,
        boolean maintenanceMode,
        String firmwareVersion,
        String aiModelVersion,
        Map<String, Compartment> compartments
) {}