import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    launchOptions: process.env.CHROMIUM_EXECUTABLE
      ? {
          executablePath: process.env.CHROMIUM_EXECUTABLE,
          args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        }
      : {},
  },
  webServer: [
    {
      command: `${process.env.TEST_PYTHON || "python3"} ../backend/tests/serve.py`,
      url: "http://127.0.0.1:8000/health",
      timeout: 60000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      timeout: 60000,
    },
  ],
});
