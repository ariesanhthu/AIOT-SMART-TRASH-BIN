package com.example.backend.service;

import com.example.backend.dto.response.DeviceTokenResponse;
import com.example.backend.exception.InvalidProvisioningSecretException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Date;

/**
 * Issues a backend-native JWT (Device Token) to ESP32 firmware after
 * verifying the provisioning secret (header X-Provision-Secret).
 *
 * The JWT payload carries { sub: deviceId, device_id: deviceId } so that
 * DeviceTokenFilter can validate the token and bind the request to the
 * correct device path without a Firebase round-trip.
 *
 * The provisioning secret is shared with the firmware at flash time and must
 * be overridden via env var DEVICE_PROVISIONING_SECRET in real deployments.
 * The JWT secret (DEVICE_JWT_SECRET) must be at least 32 characters.
 */
@Service
public class DeviceAuthService {

    private final String provisioningSecret;
    private final SecretKey jwtKey;
    private final long expirySeconds;

    public DeviceAuthService(
            @Value("${device.provisioning.secret:}") String provisioningSecret,
            @Value("${device.jwt.secret:changeme-replace-in-production-min32chars}") String jwtSecret,
            @Value("${device.jwt.expiry-seconds:86400}") long expirySeconds) {
        this.provisioningSecret = provisioningSecret;
        this.jwtKey = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
        this.expirySeconds = expirySeconds;
    }

    public DeviceTokenResponse issueDeviceToken(String deviceId, String providedSecret) {
        if (!isValidSecret(providedSecret)) {
            throw new InvalidProvisioningSecretException();
        }

        Date now = new Date();
        Date expiry = new Date(now.getTime() + expirySeconds * 1_000L);

        String token = Jwts.builder()
                .subject(deviceId)
                .claim("device_id", deviceId)
                .issuedAt(now)
                .expiration(expiry)
                .signWith(jwtKey)
                .compact();

        return new DeviceTokenResponse(deviceId, token, expirySeconds);
    }

    private boolean isValidSecret(String providedSecret) {
        if (provisioningSecret == null || provisioningSecret.isBlank() || providedSecret == null) {
            return false;
        }
        byte[] expected = provisioningSecret.getBytes(StandardCharsets.UTF_8);
        byte[] actual   = providedSecret.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, actual);
    }
}
