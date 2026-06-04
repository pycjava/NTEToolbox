import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true
  },
  test: {
    environmentMatchGlobs: [
      ["src/**/*.tsx", "jsdom"],
      ["src/**/*.test.tsx", "jsdom"]
    ],
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"]
  }
});
