package com.example.backend.model;

import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@NoArgsConstructor
public class EventData {
    @PropertyName("event_type")
    private String eventType;

    @PropertyName("waste_type")
    private String wasteType;

    @PropertyName("target_compartment")
    private String targetCompartment;

    @PropertyName("ai_confidence")
    private Double aiConfidence;

    @PropertyName("fill_percent")
    private Map<String, Double> fillPercent;

    @PropertyName("alert_threshold")
    private Double alertThreshold;

    @PropertyName("device_timestamp")
    private Timestamp deviceTimestamp;

    @PropertyName("received_at")
    private Timestamp receivedAt;

    @PropertyName("synced_late")
    private Boolean syncedLate;

    @PropertyName("firmware_version")
    private String firmwareVersion;

    @PropertyName("ai_model_version")
    private String aiModelVersion;
}