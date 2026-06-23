import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const backendPort = process.env.PIXIVDOWNLOADER_PORT ?? "7653";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        ws: true
      }
    }
  }
});
