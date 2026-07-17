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
        boolean isWrite = !"GET".equalsIgnoreCase(request.getMethod());
        // Thiết bị chưa có Firebase ID Token lúc gọi endpoint cấp token
        // (đó chính là mục đích của endpoint này) — xác thực bằng
        // provisioning secret trong DeviceAuthService thay vì filter này.
        boolean isDeviceProvisioning = path.matches(DEVICE_AUTH_TOKEN_PATTERN);
        // Chỉ áp dụng filter cho request ghi vào /api/**
        return isDeviceProvisioning || !(isApi && isWrite);
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

        try {
            FirebaseToken decoded = FirebaseAuth.getInstance().verifyIdToken(idToken);
            request.setAttribute("uid", decoded.getUid());
            request.setAttribute("email", decoded.getEmail());
        } catch (Exception e) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn");
            return;
        }

        filterChain.doFilter(request, response);
    }
}