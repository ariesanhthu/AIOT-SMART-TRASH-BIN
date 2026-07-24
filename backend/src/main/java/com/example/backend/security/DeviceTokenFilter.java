package com.example.backend.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.SecretKey;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Validates the Device JWT on the ESP32 event ingestion endpoint:
 *   POST /api/devices/{deviceId}/events
 *
 * The JWT is issued by DeviceAuthService when the ESP32 presents its
 * provisioning secret. This filter runs BEFORE FirebaseAuthFilter and is
 * the only auth check on that path (FirebaseAuthFilter excludes it).
 *
 * On success: sets request attribute "deviceId" for downstream use.
 * On failure: returns 401 immediately.
 */
@Component
public class DeviceTokenFilter extends OncePerRequestFilter {

    private static final String AUTH_HEADER    = "Authorization";
    private static final String BEARER_PREFIX  = "Bearer ";
    private static final String DEVICE_ID_ATTR = "deviceId";

    // Pattern: POST /api/devices/{deviceId}/events
    private static final String EVENT_INGEST_PATTERN = "^/api/devices/([^/]+)/events$";

    private final SecretKey jwtKey;

    public DeviceTokenFilter(
            @Value("${device.jwt.secret:changeme-replace-in-production-min32chars}") String jwtSecret) {
        this.jwtKey = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Only intercept POST /api/devices/*/events
        String path   = request.getRequestURI();
        String method = request.getMethod();
        return !("POST".equalsIgnoreCase(method) && path.matches(EVENT_INGEST_PATTERN));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String header = request.getHeader(AUTH_HEADER);
        if (header == null || !header.startsWith(BEARER_PREFIX)) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                    "Device Token missing — use Authorization: Bearer <deviceToken>");
            return;
        }

        String token = header.substring(BEARER_PREFIX.length());

        Claims claims;
        try {
            claims = Jwts.parser()
                    .verifyWith(jwtKey)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
        } catch (JwtException e) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                    "Device Token invalid or expired: " + e.getMessage());
            return;
        }

        // Verify the token's device_id claim matches the {deviceId} path variable
        String tokenDeviceId = claims.get("device_id", String.class);
        String pathDeviceId  = extractDeviceIdFromPath(request.getRequestURI());

        if (tokenDeviceId == null || !tokenDeviceId.equals(pathDeviceId)) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                    "Device Token device_id claim does not match request path");
            return;
        }

        request.setAttribute(DEVICE_ID_ATTR, tokenDeviceId);
        filterChain.doFilter(request, response);
    }

    private String extractDeviceIdFromPath(String uri) {
        // uri: /api/devices/{deviceId}/events
        String[] parts = uri.split("/");
        // parts: ["", "api", "devices", "{deviceId}", "events"]
        return parts.length >= 4 ? parts[3] : null;
    }
}
