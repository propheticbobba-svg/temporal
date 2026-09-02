import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const repoRoot = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

export default defineConfig({
  envDir: repoRoot,
  plugins: [
    {
      name: "html-build-id",
      transformIndexHtml(html) {
        // Vite writes a fixed 2018 mtime. Same-sized HTML keeps the same
        // ETag, so browsers 304 stale index.html and request a deleted JS hash.
        return html.replace("</head>", `<meta name="build" content="${Date.now()}" />\n  </head>`);
      },
    },
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      "/location": "http://localhost:8000",
      "/brief": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
