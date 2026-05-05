import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Sépare les vendors lourds dans leurs propres chunks pour réduire
        // le bundle initial et améliorer le cache HTTP entre versions
        // (un bump applicatif n'invalide pas le chunk vendor-react).
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("react-router") || id.includes("/react-dom/") || id.match(/\/react\//)) {
              return "vendor-react";
            }
            if (id.includes("motion")) {
              return "vendor-motion";
            }
            if (id.includes("i18next")) {
              return "vendor-i18n";
            }
            if (id.includes("@sentry")) {
              return "vendor-sentry";
            }
          }
          return undefined;
        },
      },
    },
  },
});
