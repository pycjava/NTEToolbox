/**
 * Copy WebView2Loader.dll from the Rust build output into src-tauri/gen/
 * so the NSIS bundler includes it via bundle.resources.
 *
 * This script is designed to run as Tauri's `beforeBundleCommand`,
 * which fires AFTER cargo build but BEFORE NSIS/MSI packaging.
 *
 * Environment variable TAURI_ENV_ARCH is set by Tauri (x86, x64, etc.).
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const clientDir = path.resolve(scriptDir, "..");
const srcTauriDir = path.resolve(clientDir, "src-tauri");
const genDir = path.resolve(srcTauriDir, "gen");

// Determine target directory (CARGO_TARGET_DIR or default target/)
const targetDir = process.env.CARGO_TARGET_DIR
  || path.join(srcTauriDir, "target");

const arch = process.env.TAURI_ENV_ARCH || "x86";
const profile = process.env.TAURI_ENV_DEBUG === "true" ? "debug" : "release";

// The DLL is placed next to the compiled exe by webview2-com-sys
const dllPath = path.join(targetDir, profile, "WebView2Loader.dll");

if (!existsSync(dllPath)) {
  // Try debug fallback (useful for first-time builds)
  const fallbackPath = path.join(targetDir, "debug", "WebView2Loader.dll");
  if (!existsSync(fallbackPath)) {
    console.warn(`[copy-webview-dll] WebView2Loader.dll not found at ${dllPath} or ${fallbackPath}, skipping`);
    process.exit(0);
  }
  console.log(`[copy-webview-dll] Using fallback: ${fallbackPath}`);
  cpSync(fallbackPath, path.join(genDir, "WebView2Loader.dll"));
} else {
  mkdirSync(genDir, { recursive: true });
  cpSync(dllPath, path.join(genDir, "WebView2Loader.dll"));
  console.log(`[copy-webview-dll] Copied WebView2Loader.dll -> gen/ (${arch}/${profile})`);
}
