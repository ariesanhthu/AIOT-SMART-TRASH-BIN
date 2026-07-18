import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const cameraTarget = trimTrailingSlash(
    env.ESP32_CAMERA_URL || "http://172.20.10.2",
  );
  const streamTarget = trimTrailingSlash(
    env.ESP32_STREAM_URL || `${cameraTarget}:81`,
  );

  return {
    plugins: [react()],

    server: {
      host: "0.0.0.0",
      port: 5173,

      proxy: {
        "/capture": {
          target: cameraTarget,
          changeOrigin: true,
        },

        "/stream": {
          target: streamTarget,
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
        },
      },
    },
  };
});
