const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.STUDIO_BROWSER ||
      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    headless: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(process.env.NAMEBENCH_URL || "http://127.0.0.1:5001");
    await page.waitForSelector(".form-row");
    assert.equal(await page.locator("html").getAttribute("lang"), "en");
    assert.equal(await page.locator("h1").textContent(), "Namebench");
    await page.locator(".type-select").selectOption("fullname");
    await page.click("#btn-generate");
    await page.waitForSelector("#results-section:not(.hidden)");
    assert.ok((await page.locator("#results-grid").innerText()).length > 20);
    const download = page.waitForEvent("download");
    await page.click("#btn-export-json");
    const saved = await download;
    const content = JSON.parse(fs.readFileSync(await saved.path(), "utf8"));
    assert.ok(content.length);
    fs.mkdirSync("output/screenshots", { recursive: true });
    await page.screenshot({ path: "output/screenshots/namebench-desktop.png", fullPage: true });
    await page.click('[data-domain="places"]');
    await page.locator(".group-header").first().click();
    await page.locator('.style-entry[data-id="FR"]').first().click();
    await page.click("#btn-generate");
    await page.waitForTimeout(250);
    assert.ok((await page.locator("#results-grid").innerText()).length > 20);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: "output/screenshots/namebench-mobile.png", fullPage: true });
    assert.deepEqual(errors, []);
    console.log("Namebench browser: names, places, JSON export, desktop and mobile passed.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
