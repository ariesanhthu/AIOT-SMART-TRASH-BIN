package com.example.backend.model;

import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import lombok.NoArgsConstructor;

import java.util.Map;

@NoArgsConstructor
public class Device {
    private String name;
    private String location;
    private Timestamp lastSeenAt;
    private Boolean maintenanceMode;
    private String firmwareVersion;
    private String aiModelVersion;
    private Map<String, Compartment> compartments;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getLocation() { return location; }
    public void setLocation(String location) { this.location = location; }

    @PropertyName("last_seen_at")
    public Timestamp getLastSeenAt() { return lastSeenAt; }
    @PropertyName("last_seen_at")
    public void setLastSeenAt(Timestamp lastSeenAt) { this.lastSeenAt = lastSeenAt; }

    @PropertyName("maintenance_mode")
    public Boolean getMaintenanceMode() { return maintenanceMode; }
    @PropertyName("maintenance_mode")
    public void setMaintenanceMode(Boolean maintenanceMode) { this.maintenanceMode = maintenanceMode; }

    @PropertyName("firmware_version")
    public String getFirmwareVersion() { return firmwareVersion; }
    @PropertyName("firmware_version")
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }

    @PropertyName("ai_model_version")
    public String getAiModelVersion() { return aiModelVersion; }
    @PropertyName("ai_model_version")
    public void setAiModelVersion(String aiModelVersion) { this.aiModelVersion = aiModelVersion; }

    public Map<String, Compartment> getCompartments() { return compartments; }
    public void setCompartments(Map<String, Compartment> compartments) { this.compartments = compartments; }
}