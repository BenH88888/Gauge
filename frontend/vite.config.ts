import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base URL is configurable so the same build can point at a
// local backend during development or a deployed one in production.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Prioritise TypeScript sources over any stale compiled .js twins.
    extensions: [".tsx", ".ts", ".jsx", ".mjs", ".js", ".json"],
  },
  server: {
    port: 5173,
    strictPort: false,
  },
});
