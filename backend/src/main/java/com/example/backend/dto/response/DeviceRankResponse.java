package com.example.backend.dto.response;

public record DeviceRankResponse (
    String deviceId,
    long totalCount
) {}
