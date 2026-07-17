package com.example.backend.model;

import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@NoArgsConstructor
public class Device {
    private String name;
    private String location;

    @PropertyName("last_seen_at")
    private Timestamp lastSeenAt;

    @PropertyName("maintenance_mode")
    private Boolean maintenanceMode;

    @PropertyName("firmware_version")
    private String firmwareVersion;

    @PropertyName("ai_model_version")
    private String aiModelVersion;

    private Map<String, Compartment> compartments;
}