package com.example.backend.service;

import com.example.backend.dto.request.UpdateDeviceConfigRequest;
import com.example.backend.dto.response.DeviceResponse;
import com.example.backend.exception.DeviceNotFoundException;
import com.example.backend.model.Device;
import com.google.cloud.Timestamp;
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.QuerySnapshot;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class DeviceService {

    private static final String COLLECTION = "devices";

    private final Firestore firestore;

    public DeviceService(Firestore firestore) {
        this.firestore = firestore;
    }

    public List<DeviceResponse> getAllDevices() {
        QuerySnapshot snapshot;
        try {
            snapshot = firestore.collection(COLLECTION).get().get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bị gián đoạn khi đọc Firestore", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi đọc Firestore", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }

        return snapshot.getDocuments().stream()
                .map(this::toDeviceResponse)
                .collect(Collectors.toList());
    }

    public DeviceResponse getDeviceById(String deviceId) {
        DocumentSnapshot snapshot;
        try {
            snapshot = firestore.collection(COLLECTION).document(deviceId).get().get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bị gián đoạn khi đọc Firestore", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi đọc Firestore", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }

        if (!snapshot.exists()) {
            throw new DeviceNotFoundException(deviceId);
        }

        return toDeviceResponse(snapshot);
    }

    public void updateConfig(String deviceId, UpdateDeviceConfigRequest request, String updatedByEmail) {
        DocumentReference docRef = firestore.collection(COLLECTION).document(deviceId);

        try {
            if (!docRef.get().get().exists()) {
                throw new DeviceNotFoundException(deviceId);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bị gián đoạn khi đọc Firestore", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi đọc Firestore", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }

        Map<String, Object> updates = new HashMap<>();

        if (request.thresholds() != null) {
            request.thresholds().forEach((compartment, value) ->
                    updates.put("compartments." + compartment + ".threshold", value));
        }

        if (request.maintenanceMode() != null) {
            updates.put("maintenance_mode", request.maintenanceMode());
        }

        if (updates.isEmpty()) {
            return;
        }

        updates.put("last_config_updated_by", updatedByEmail);
        updates.put("last_config_updated_at", Timestamp.now());

        try {
            docRef.update(updates).get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Bị gián đoạn khi ghi Firestore", e);
        } catch (ExecutionException e) {
            log.error("Lỗi khi ghi Firestore", e.getCause());
            throw new RuntimeException("Lỗi khi đọc Firestore", e.getCause());
        }
    }

    private DeviceResponse toDeviceResponse(DocumentSnapshot snapshot) {
        Device device = snapshot.toObject(Device.class);
        if (device == null) {
            throw new DeviceNotFoundException(snapshot.getId());
        }

        return new DeviceResponse(
                snapshot.getId(),
                device.getName(),
                device.getLocation(),
                device.getLastSeenAt() != null ? device.getLastSeenAt().toDate().toInstant().toString() : null,
                Boolean.TRUE.equals(device.getMaintenanceMode()),
                device.getFirmwareVersion(),
                device.getAiModelVersion(),
                device.getClassName(),
                device.getCompartments()
        );
    }
}