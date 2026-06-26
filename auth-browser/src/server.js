import express from "express";
import { chromium } from "playwright";

const PORT = Number(process.env.PIXIV_AUTH_BROWSER_PORT || "7654");
const DISPLAY = process.env.DISPLAY || ":99";
const TOKEN = (process.env.PIXIV_AUTH_BROWSER_TOKEN || "").trim();
const CALLBACK_MATCH = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback";
const USER_AGENT = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)";

const app = express();
app.use(express.json({ limit: "64kb" }));

let activeSession = null;

app.get("/health", (_request, response) => {
  response.json({ status: "ok" });
});

app.post("/api/auth/start", async (request, response) => {
  if (!authorized(request)) {
    response.status(401).json({ error: "unauthorized" });
    return;
  }

  const { flow_id: flowId, login_url: loginUrl, callback_url: callbackUrl } = request.body || {};
  if (!flowId || !loginUrl || !callbackUrl) {
    response.status(400).json({ error: "flow_id, login_url, and callback_url are required" });
    return;
  }

  try {
    await closeActiveSession();
    activeSession = await startBrowserSession({ flowId, loginUrl, callbackUrl });
    response.json({ ok: true });
  } catch (error) {
    await notifyBackend({
      callbackUrl,
      flowId,
      payload: { flow_id: flowId, error: errorMessage(error) }
    });
    response.status(500).json({ error: errorMessage(error) });
  }
});

async function startBrowserSession({ flowId, loginUrl, callbackUrl }) {
  const browser = await chromium.launch({
    headless: false,
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--window-size=1280,900"
    ],
    env: {
      ...process.env,
      DISPLAY
    }
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent: USER_AGENT
  });
  const page = await context.newPage();
  let finished = false;

  const finish = async (payload) => {
    if (finished) {
      return;
    }
    finished = true;
    try {
      await notifyBackend({ callbackUrl, flowId, payload });
      await showResultPage(page, {
        title: "Pixiv authentication succeeded",
        message: "Token saved. Please return to PixivDownloader.",
        tone: "success"
      });
    } catch (error) {
      console.error(error);
      await showResultPage(page, {
        title: "Pixiv authentication failed",
        message: "PixivDownloader could not save the token. Please return and try again.",
        tone: "error"
      });
    }
  };

  page.on("request", (browserRequest) => {
    const url = browserRequest.url();
    if (url.startsWith(CALLBACK_MATCH)) {
      void finish({ flow_id: flowId, callback_url: url });
    }
  });
  page.on("framenavigated", (frame) => {
    const url = frame.url();
    if (url.startsWith(CALLBACK_MATCH)) {
      void finish({ flow_id: flowId, callback_url: url });
    }
  });
  page.on("pageerror", (error) => {
    console.error(error);
  });

  await page.goto(loginUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  return { browser };
}

async function closeActiveSession() {
  if (!activeSession) {
    return;
  }
  const session = activeSession;
  activeSession = null;
  await session.browser.close().catch(() => {});
}

async function notifyBackend({ callbackUrl, flowId, payload }) {
  const headers = { "Content-Type": "application/json" };
  if (TOKEN) {
    headers["X-Pixiv-Auth-Browser-Token"] = TOKEN;
  }
  const response = await fetch(callbackUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Backend rejected Pixiv auth callback for ${flowId}: ${response.status} ${body}`);
  }
}

async function showResultPage(page, { title, message, tone }) {
  const colors =
    tone === "success"
      ? { bg: "#0f1f1a", border: "#2f8f6b", accent: "#7dd3a8" }
      : { bg: "#241516", border: "#b24b55", accent: "#f0a0a8" };
  await page.setContent(
    `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: ${colors.bg};
      color: #f7faf8;
      font-family: Arial, sans-serif;
    }
    main {
      width: min(560px, calc(100vw - 48px));
      border: 1px solid ${colors.border};
      border-radius: 8px;
      padding: 28px;
      background: rgba(255, 255, 255, 0.06);
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
    }
    h1 {
      margin: 0 0 12px;
      color: ${colors.accent};
      font-size: 24px;
      line-height: 1.25;
    }
    p {
      margin: 0;
      font-size: 16px;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <main>
    <h1>${escapeHtml(title)}</h1>
    <p>${escapeHtml(message)}</p>
  </main>
</body>
</html>`,
    { waitUntil: "domcontentloaded" }
  );
}

function authorized(request) {
  if (!TOKEN) {
    return true;
  }
  return request.get("X-Pixiv-Auth-Browser-Token") === TOKEN;
}

function errorMessage(error) {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Pixiv auth browser API listening on ${PORT}`);
});
