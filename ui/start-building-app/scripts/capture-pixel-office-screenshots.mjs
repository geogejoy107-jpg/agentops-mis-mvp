import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.PIXEL_OFFICE_BASE_URL || "http://127.0.0.1:4173";
const outputDir = path.resolve(process.env.PIXEL_OFFICE_SCREENSHOT_DIR || "./artifacts/pixel-office-screenshots");
const route = `${baseUrl}/workspace/pixel-office`;
const themes = ["harvest-commons", "orbital-deck"];

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const captured = [];

try {
  for (const themeId of themes) {
    const context = await browser.newContext({
      viewport: { width: 1600, height: 1120 },
      deviceScaleFactor: 1,
      locale: "zh-CN",
      reducedMotion: "reduce",
      colorScheme: "dark",
    });

    await context.addInitScript(({ selectedTheme }) => {
      window.localStorage.setItem("agentops-mis-locale", "zh");
      window.localStorage.setItem("agentops-mis-theme", "ops");
      window.localStorage.setItem("agentops.pixel-office.theme.v1", selectedTheme);
    }, { selectedTheme: themeId });

    const page = await context.newPage();
    await page.goto(route, { waitUntil: "networkidle", timeout: 90_000 });
    await page.getByTestId("pixel-office-theme-selector").waitFor({ state: "visible", timeout: 30_000 });

    const themeButton = page.locator(`[data-theme-id="${themeId}"]`);
    await themeButton.click();
    await page.locator(`[data-theme-id="${themeId}"][aria-checked="true"]`).waitFor({ state: "visible" });

    await page.addStyleTag({
      content: `
        html { scroll-behavior: auto !important; }
        * { caret-color: transparent !important; }
        ::-webkit-scrollbar { width: 0 !important; height: 0 !important; }
        .pixel-ambient-motion, .pixel-agent-motion { animation: none !important; }
      `,
    });

    await page.evaluate(() => {
      document.querySelector('[data-testid="pixel-office-theme-selector"]')?.scrollIntoView({ block: "start" });
      window.scrollBy(0, -12);
    });
    await page.waitForTimeout(350);

    const screenshotPath = path.join(outputDir, `pixel-office-${themeId}.png`);
    await page.screenshot({
      path: screenshotPath,
      fullPage: false,
      animations: "disabled",
    });
    captured.push({ themeId, file: path.basename(screenshotPath) });

    if (themeId === themes[0]) {
      const galleryPath = path.join(outputDir, "pixel-office-theme-gallery.png");
      await page.getByTestId("pixel-office-theme-selector").screenshot({
        path: galleryPath,
        animations: "disabled",
      });
      captured.push({ themeId: "gallery", file: path.basename(galleryPath) });
    }

    await context.close();
  }
} finally {
  await browser.close();
}

await writeFile(
  path.join(outputDir, "manifest.json"),
  `${JSON.stringify({ route, capturedAt: new Date().toISOString(), captured }, null, 2)}\n`,
  "utf8",
);

console.log(`Captured ${captured.length} Pixel Office screenshots in ${outputDir}`);
