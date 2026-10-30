import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // During development, Vite serves the page and forwards /api calls to FastAPI.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    // The app loads from your own disk, so bundle size barely matters (recharts alone is big).
    chunkSizeWarningLimit: 1000,
  },
  test: {
    environment: "node", // the tests cover plain functions, so no browser is needed
  },
});
