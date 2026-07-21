package com.example.backend.model;

import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import lombok.NoArgsConstructor;

import java.util.Map;

@NoArgsConstructor
public class EventData {
    private String eventType;
    private String wasteType;
    private String targetCompartment;
    private Double aiConfidence;
    private Map<String, Double> fillPercent;
    private Double alertThreshold;
    private Timestamp deviceTimestamp;
    private Timestamp receivedAt;
    private Boolean syncedLate;
    private String firmwareVersion;
    private String aiModelVersion;
    private String alertStatus;
    private Timestamp resolvedAt;
    private String resolvedBy;
    private String imageUrl;

    @PropertyName("event_type")
    public String getEventType() { return eventType; }
    @PropertyName("event_type")
    public void setEventType(String eventType) { this.eventType = eventType; }

    @PropertyName("waste_type")
    public String getWasteType() { return wasteType; }
    @PropertyName("waste_type")
    public void setWasteType(String wasteType) { this.wasteType = wasteType; }

    @PropertyName("target_compartment")
    public String getTargetCompartment() { return targetCompartment; }
    @PropertyName("target_compartment")
    public void setTargetCompartment(String targetCompartment) { this.targetCompartment = targetCompartment; }

    @PropertyName("ai_confidence")
    public Double getAiConfidence() { return aiConfidence; }
    @PropertyName("ai_confidence")
    public void setAiConfidence(Double aiConfidence) { this.aiConfidence = aiConfidence; }

    @PropertyName("fill_percent")
    public Map<String, Double> getFillPercent() { return fillPercent; }
    @PropertyName("fill_percent")
    public void setFillPercent(Map<String, Double> fillPercent) { this.fillPercent = fillPercent; }

    @PropertyName("alert_threshold")
    public Double getAlertThreshold() { return alertThreshold; }
    @PropertyName("alert_threshold")
    public void setAlertThreshold(Double alertThreshold) { this.alertThreshold = alertThreshold; }

    @PropertyName("device_timestamp")
    public Timestamp getDeviceTimestamp() { return deviceTimestamp; }
    @PropertyName("device_timestamp")
    public void setDeviceTimestamp(Timestamp deviceTimestamp) { this.deviceTimestamp = deviceTimestamp; }

    @PropertyName("received_at")
    public Timestamp getReceivedAt() { return receivedAt; }
    @PropertyName("received_at")
    public void setReceivedAt(Timestamp receivedAt) { this.receivedAt = receivedAt; }

    @PropertyName("synced_late")
    public Boolean getSyncedLate() { return syncedLate; }
    @PropertyName("synced_late")
    public void setSyncedLate(Boolean syncedLate) { this.syncedLate = syncedLate; }

    @PropertyName("firmware_version")
    public String getFirmwareVersion() { return firmwareVersion; }
    @PropertyName("firmware_version")
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }

    @PropertyName("ai_model_version")
    public String getAiModelVersion() { return aiModelVersion; }
    @PropertyName("ai_model_version")
    public void setAiModelVersion(String aiModelVersion) { this.aiModelVersion = aiModelVersion; }

    @PropertyName("alert_status")
    public String getAlertStatus() { return alertStatus; }
    @PropertyName("alert_status")
    public void setAlertStatus(String alertStatus) { this.alertStatus = alertStatus; }

    @PropertyName("resolved_at")
    public Timestamp getResolvedAt() { return resolvedAt; }
    @PropertyName("resolved_at")
    public void setResolvedAt(Timestamp resolvedAt) { this.resolvedAt = resolvedAt; }

    @PropertyName("resolved_by")
    public String getResolvedBy() { return resolvedBy; }
    @PropertyName("resolved_by")
    public void setResolvedBy(String resolvedBy) { this.resolvedBy = resolvedBy; }

    @PropertyName("image_url")
    public String getImageUrl() { return imageUrl; }
    @PropertyName("image_url")
    public void setImageUrl(String imageUrl) { this.imageUrl = imageUrl; }
}