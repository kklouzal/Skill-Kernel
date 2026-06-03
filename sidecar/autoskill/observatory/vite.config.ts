import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  build: {
    sourcemap: true,
    target: "es2022",
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("echarts") || id.includes("zrender")) return "charts";
          if (id.includes("elkjs")) return "elk";
          if (id.includes("@xyflow")) return "graph";
          if (id.includes("monaco-editor") || id.includes("@monaco-editor")) return "monaco";
          if (id.includes("pixi.js")) return "pixi";
          if (id.includes("lucide-react")) return "icons";
          return "vendor";
        }
      }
    }
  },
  server: {
    proxy: {
      "/admin/api": "http://127.0.0.1:8765",
      "/admin/live": {
        target: "ws://127.0.0.1:8765",
        ws: true
      }
    }
  }
});
