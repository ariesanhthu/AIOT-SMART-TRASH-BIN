package com.example.backend.controller;

import com.example.backend.dto.response.DeviceTokenResponse;
import com.example.backend.service.DeviceAuthService;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/devices")
public class DeviceAuthController {

    private final DeviceAuthService deviceAuthService;

    public DeviceAuthController(DeviceAuthService deviceAuthService) {
        this.deviceAuthService = deviceAuthService;
    }

    @PostMapping("/{deviceId}/auth-token")
    public DeviceTokenResponse issueToken(
            @PathVariable String deviceId,
            @RequestHeader("X-Provision-Secret") String provisionSecret
    ) {
        return deviceAuthService.issueDeviceToken(deviceId, provisionSecret);
    }
}
