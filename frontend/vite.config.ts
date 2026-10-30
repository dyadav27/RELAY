import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to FastAPI so the browser always uses same-origin /api routes.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
