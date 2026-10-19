import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves the site from /<repo-name>/. VITE_BASE is set by the workflow; "/" for local dev.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"] },
});
