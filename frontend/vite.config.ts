import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const repoRoot = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

export default defineConfig({
  envDir: repoRoot,
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/location": "http://localhost:8000",
      "/brief": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
