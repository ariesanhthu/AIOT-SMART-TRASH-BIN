package com.example.backend.dto.response;

public record DeviceTokenResponse(
        String deviceId,
        String token,
        long expiresInSeconds
) {}
