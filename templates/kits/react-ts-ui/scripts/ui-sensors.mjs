// UI sensors (contracts/ui-stories.md section 8): axe (WCAG 2.2 AA) and a Core Web Vitals budget, per page.
//
//   npm run ui:sensors -- --out <central>/docs/qa/<F>/<S>-sensors --budget "LCP 2500, CLS 0.1, INP 200" \
//     [--screenshot <central>/docs/architecture/screens/<screen-id>/built.png] URL [URL ...]
//
// URL: the built screen on a running dev or preview server, or a wireframe option as a file:// URL.
// Writes axe.json ([{url, violations}]) and web-vitals.json ([{url, lcp, cls, inp, over}]). Exit 1 on a serious or
// critical axe violation; over budget is reported, not failed (contracts/ui-stories.md section 8). Playwright's
// browser comes from the org's mirror (PLAYWRIGHT_DOWNLOAD_HOST); nothing is fetched from the internet.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "@playwright/test";

const args = process.argv.slice(2);
const take = (flag) => {
  const at = args.indexOf(flag);
  return at === -1 ? undefined : args.splice(at, 2)[1];
};
const out = take("--out");
const budgetText = take("--budget") ?? "LCP 2500, CLS 0.1, INP 200";
const screenshot = take("--screenshot");
if (!out || args.length === 0) {
  console.error("usage: ui-sensors --out DIR [--budget TEXT] [--screenshot FILE] URL [URL ...]");
  process.exit(2);
}
const budget = Object.fromEntries(
  budgetText.split(",").map((part) => part.trim().split(/\s+/)).map(([k, v]) => [k.toUpperCase(), Number(v)]),
);

const browser = await chromium.launch();
const axe = [];
const vitals = [];
for (const url of args) {
  const page = await browser.newPage();
  await page.addInitScript(() => {
    window.__vitals = { lcp: 0, cls: 0 };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__vitals.lcp = entry.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__vitals.cls += entry.value;
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.goto(url, { waitUntil: "networkidle" });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  axe.push({ url, violations: result.violations.map(({ id, impact, help, nodes }) => ({ id, impact, help, nodes: nodes.length })) });
  const measured = await page.evaluate(() => window.__vitals);
  const row = { url, lcp: Math.round(measured.lcp), cls: Number(measured.cls.toFixed(3)), inp: null };
  row.over = ["LCP", "CLS"].filter((k) => budget[k] !== undefined && row[k.toLowerCase()] > budget[k]);
  vitals.push(row);
  if (screenshot && url === args[0]) await page.screenshot({ path: screenshot, fullPage: true });
  await page.close();
}
await browser.close();

mkdirSync(out, { recursive: true });
writeFileSync(join(out, "axe.json"), JSON.stringify(axe, null, 1) + "\n");
writeFileSync(join(out, "web-vitals.json"), JSON.stringify(vitals, null, 1) + "\n");
const serious = axe.flatMap((p) => p.violations).filter((v) => v.impact === "serious" || v.impact === "critical");
console.log(`axe: ${serious.length} serious or critical; web vitals over budget: ${vitals.filter((v) => v.over.length).length} pages`);
process.exit(serious.length ? 1 : 0);
