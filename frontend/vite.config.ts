/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The backend serves no CORS headers (see FINDINGS.md), so the app talks to it through a
// same-origin `/api` prefix that the dev and preview servers proxy.
const target = process.env.EPV_API ?? "http://localhost:8000";
const proxy = {
  "/api": { target, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
