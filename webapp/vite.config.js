import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend (run `docker compose up -d app`
// separately, then `npm run dev` here). Production build output goes straight
// into app/static, which FastAPI serves directly — see main.py.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
});
