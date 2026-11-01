import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app";
import { startPush } from "./lib/push";
import "./styles.css";

startPush();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
