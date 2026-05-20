import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base URL is configurable so the same build can point at a
// local backend during development or a deployed one in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
});
