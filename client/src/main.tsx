import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import HsOverlay from "./HsOverlay";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./styles/tokens.css";
import "./styles/app.css";

// 悬浮窗窗口（label "hs-overlay"）渲染精简 UI，主窗口渲染完整 App
const isOverlay = typeof window !== "undefined" && getCurrentWindow().label === "hs-overlay";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {isOverlay ? <HsOverlay /> : <App />}
  </React.StrictMode>
);
