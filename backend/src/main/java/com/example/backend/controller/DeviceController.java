package com.example.backend.controller;

import com.example.backend.dto.request.UpdateDeviceConfigRequest;
import com.example.backend.dto.response.DeviceResponse;
import com.example.backend.service.DeviceService;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/devices")
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @GetMapping
    public List<DeviceResponse> getAllDevices() {
        return deviceService.getAllDevices();
    }

    @GetMapping("/{deviceId}")
    public DeviceResponse getDevice(@PathVariable String deviceId) {
        return deviceService.getDeviceById(deviceId);
    }

    @PatchMapping("/{deviceId}/config")
    public ResponseEntity<Void> updateConfig(
            @PathVariable String deviceId,
            @RequestBody UpdateDeviceConfigRequest request,
            HttpServletRequest httpRequest
    ) {
        String email = (String) httpRequest.getAttribute("email");
        deviceService.updateConfig(deviceId, request, email);
        return ResponseEntity.noContent().build();
    }
}