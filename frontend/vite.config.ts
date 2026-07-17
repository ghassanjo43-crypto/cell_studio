/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // The WebXR emulator devtools (@iwer/devui) conflicts with R3F v8's zustand
      // and is dev-only; stub it out. Real-headset VR is unaffected.
      "@iwer/devui": fileURLToPath(new URL("./src/vendor/iwer-devui-stub.ts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Proxy API + WebSocket to the backend during local development so the app
    // can use same-origin relative URLs.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
