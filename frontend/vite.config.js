import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/location": "http://localhost:8000",
      "/brief": "http://localhost:8000",
    },
  },
});
