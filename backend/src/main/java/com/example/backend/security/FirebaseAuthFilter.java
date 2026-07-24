package com.example.backend.security;

import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseToken;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Chặn request ghi (POST/PATCH/PUT/DELETE) vào /api/**, yêu cầu header
 * Authorization: Bearer <Firebase ID Token>. Request đọc (GET) được đi qua
 * tự do để dễ test và vì dashboard xem trạng thái không cần xác thực gắt
 * theo NFREQ.14 (chỉ "tính năng quản trị" mới bắt buộc xác thực).
 */
@Component
public class FirebaseAuthFilter extends OncePerRequestFilter {

    private static final String AUTH_HEADER = "Authorization";
    private static final String BEARER_PREFIX = "Bearer ";

    private static final String DEVICE_AUTH_TOKEN_PATTERN = "^/api/devices/[^/]+/auth-token$";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        boolean isApi = path.startsWith("/api/");
        boolean isPreflight = "OPTIONS".equalsIgnoreCase(request.getMethod());
        boolean isWrite = !"GET".equalsIgnoreCase(request.getMethod()) && !isPreflight;
        // Thiết bị chưa có Firebase ID Token lúc gọi endpoint cấp token
        // (đó chính là mục đích của endpoint này) — xác thực bằng
        // provisioning secret trong DeviceAuthService thay vì filter này.
        boolean isDeviceProvisioning = path.matches(DEVICE_AUTH_TOKEN_PATTERN);
        // ESP32 event ingestion — authenticated by DeviceTokenFilter (Device JWT),
        // not by Firebase ID Token. Exclude from this filter so both can coexist.
        boolean isDeviceEventIngestion = path.matches("^/api/devices/[^/]+/events$")
                && "POST".equalsIgnoreCase(request.getMethod());
        // Chỉ áp dụng filter cho request ghi vào /api/**
        return isDeviceProvisioning || isDeviceEventIngestion || !(isApi && isWrite);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String header = request.getHeader(AUTH_HEADER);

        if (header == null || !header.startsWith(BEARER_PREFIX)) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Thiếu Firebase ID Token");
            return;
        }

        String idToken = header.substring(BEARER_PREFIX.length());
        FirebaseToken decoded = null;
        Exception lastError = null;
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                decoded = FirebaseAuth.getInstance().verifyIdToken(idToken);
                break;
            } catch (Exception e) {
                lastError = e;
                if (attempt < 3) {
                    try { Thread.sleep(300); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
                }
            }
        }
        if (decoded == null) {
            if (lastError != null) lastError.printStackTrace();
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn");
            return;
        }
        request.setAttribute("uid", decoded.getUid());
        request.setAttribute("email", decoded.getEmail());

        filterChain.doFilter(request, response);
    }
}