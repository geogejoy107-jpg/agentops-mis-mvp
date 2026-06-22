import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

await mkdir("visual-artifacts", { recursive: true });
const browser = await chromium.launch({ headless: true });
const targets = [
  { name: "mission-control-1440x900-light-zh", width: 1440, height: 900, theme: "enterprise", locale: "zh", path: "/workspace" },
  { name: "mission-control-1024x768-dark-en", width: 1024, height: 768, theme: "ops", locale: "en", path: "/workspace" },
  { name: "mission-control-390x844-dark-zh", width: 390, height: 844, theme: "ops", locale: "zh", path: "/workspace" },
  { name: "pixel-office-1440x900", width: 1440, height: 900, theme: "ops", locale: "zh", path: "/pixel-office" },
];

async function openTarget(target) {
  const page = await browser.newPage({ viewport: { width: target.width, height: target.height } });
  await page.addInitScript(({ theme, locale }) => {
    localStorage.setItem("agentops-mis-theme", theme);
    localStorage.setItem("agentops-mis-locale", locale);
  }, { theme: target.theme, locale: target.locale });
  await page.goto("http://127.0.0.1:5173" + target.path, { waitUntil: "networkidle" });
  await page.locator("main").waitFor({ state: "visible" });
  return page;
}

for (const target of targets) {
  const page = await openTarget(target);
  await page.screenshot({ path: `visual-artifacts/${target.name}.png`, animations: "disabled" });
  await page.close();
}

const missionPreview = await openTarget({ width: 1440, height: 900, theme: "ops", locale: "zh", path: "/workspace" });
const missionMapMarker = missionPreview.getByText("原生 React / CSS 工作台", { exact: true }).last();
await missionMapMarker.waitFor({ state: "visible", timeout: 15000 });
await missionMapMarker.scrollIntoViewIfNeeded();
await missionPreview.waitForTimeout(250);
await missionPreview.screenshot({ path: "visual-artifacts/mission-control-pixel-preview-1440x900.png", animations: "disabled" });
await missionPreview.close();

const pixelMap = await openTarget({ width: 1440, height: 900, theme: "ops", locale: "zh", path: "/pixel-office" });
const pixelMapMarker = pixelMap.getByText("原生 React / CSS 工作台", { exact: true }).last();
await pixelMapMarker.waitFor({ state: "visible", timeout: 15000 });
await pixelMapMarker.scrollIntoViewIfNeeded();
await pixelMap.waitForTimeout(250);
await pixelMap.screenshot({ path: "visual-artifacts/pixel-office-map-1440x900.png", animations: "disabled" });
await pixelMap.close();

await browser.close();
