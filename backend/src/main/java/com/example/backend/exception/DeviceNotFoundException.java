package com.example.backend.exception;

public class DeviceNotFoundException extends RuntimeException {
    public DeviceNotFoundException(String deviceId) {
        super("Không tìm thấy thiết bị với device_id = " + deviceId);
    }
}