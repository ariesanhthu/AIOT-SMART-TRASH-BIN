package com.example.backend.service;

import com.example.backend.dto.response.DeviceTokenResponse;
import com.example.backend.exception.InvalidProvisioningSecretException;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

/**
 * Cấp Firebase custom token cho ESP32, gắn claim device_id để Firestore
 * Security Rules giới hạn thiết bị chỉ đọc/ghi đúng path của nó (xem
 * docs/architecture/De_xuat_thiet_ke_DB.md mục 2.1, NFREQ.15). Endpoint này
 * không dùng FirebaseAuthFilter (thiết bị chưa có ID Token lúc gọi), thay
 * vào đó xác thực bằng provisioning secret chia sẻ trước, nạp vào firmware
 * lúc flash.
 */
@Service
public class DeviceAuthService {

    private final String provisioningSecret;

    public DeviceAuthService(@Value("${device.provisioning.secret:}") String provisioningSecret) {
        this.provisioningSecret = provisioningSecret;
    }

    public DeviceTokenResponse issueDeviceToken(String deviceId, String providedSecret) {
        if (!isValidSecret(providedSecret)) {
            throw new InvalidProvisioningSecretException();
        }

        try {
            String customToken = FirebaseAuth.getInstance()
                    .createCustomToken(deviceId, Map.of("device_id", deviceId));
            return new DeviceTokenResponse(deviceId, customToken);
        } catch (FirebaseAuthException e) {
            throw new RuntimeException("Không thể tạo custom token cho thiết bị " + deviceId, e);
        }
    }

    private boolean isValidSecret(String providedSecret) {
        if (provisioningSecret == null || provisioningSecret.isBlank() || providedSecret == null) {
            return false;
        }
        byte[] expected = provisioningSecret.getBytes(StandardCharsets.UTF_8);
        byte[] actual = providedSecret.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, actual);
    }
}
