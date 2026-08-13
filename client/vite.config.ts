import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    // 修复：src-tauri/target（3.7GB Rust 构建产物）与 gen/ 不应触发
    // HMR/监听，否则 dev/watch 模式 CPU 打满。
    watch: {
      ignored: ["**/src-tauri/**", "**/gen/**"]
    }
  },
  test: {
    environmentMatchGlobs: [
      ["src/**/*.tsx", "jsdom"],
      ["src/**/*.test.tsx", "jsdom"]
    ],
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    // 修复：`npx vitest`（watch 模式）默认监听整个项目根，会把
    // src-tauri/target（3.7GB、8000+ 文件）全部纳入监听 → CPU 打满。
    watchExclude: ["**/src-tauri/**", "**/gen/**", "**/node_modules/**"]
  }
});
