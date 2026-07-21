import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const cameraUrl = new URL(
    env.ESP32_CAMERA_URL || "http://172.20.10.2",
  );

  const streamUrl = env.ESP32_STREAM_URL
    ? new URL(env.ESP32_STREAM_URL)
    : new URL(cameraUrl.origin);

  // Nếu không cấu hình riêng stream URL thì dùng IP camera với port 81.
  if (!env.ESP32_STREAM_URL) {
    streamUrl.port = "81";
  }

  return {
    plugins: [react()],

    server: {
      host: "0.0.0.0",
      port: 5173,

      proxy: {
        "/capture": {
          target: cameraUrl.origin,
          changeOrigin: true,
        },

        "/stream": {
          target: streamUrl.origin,
          changeOrigin: true,

          // Giữ kết nối MJPEG stream mở lâu dài.
          timeout: 0,
          proxyTimeout: 0,
        },
      },
    },
  };
});