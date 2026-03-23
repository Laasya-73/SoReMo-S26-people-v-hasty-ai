import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  build: {
    chunkSizeWarningLimit: 2200,
    rollupOptions: {
      onwarn(warning, warn) {
        const message = String(warning?.message || "");
        const importer = String(warning?.id || warning?.exporter || "");
        const isLoadersGlSpawnWarning =
          warning?.code === "MISSING_EXPORT" &&
          message.includes("\"spawn\" is not exported by \"__vite-browser-external\"") &&
          importer.includes("child-process-proxy.js");
        if (isLoadersGlSpawnWarning) return;
        warn(warning);
      },
      output: {
        manualChunks: {
          mapstack: ["maplibre-gl", "@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox"],
          pdf: ["jspdf"]
        }
      }
    }
  },
  server: {
    host: "0.0.0.0",
    port: 5173
  }
});
