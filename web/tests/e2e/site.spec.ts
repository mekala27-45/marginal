import { expect, test } from "@playwright/test";

import { formatValue } from "../../src/lib/format";

import { bundle, collectErrors, manifest, open, ready, recorded, ROUTES } from "./site";

const printed = (key: string) => {
  const entry = manifest.values[key];
  if (!entry) throw new Error(`the manifest has no ${key}`);
  return formatValue(entry.value, entry.fmt);
};

test("the overview shows both headline budget numbers and the statement", async ({ page }) => {
  await open(page, "/");
  const gain = page.getByTestId("headline-gain-value");
  const share = page.getByTestId("headline-share-value");
  await expect(gain).toContainText("$");
  await expect(share).toContainText("%");
  await expect(gain).toHaveText(printed("budget.headline.gain_over_last_year_annual"));
  await expect(share).toHaveText(printed("budget.headline.share_captured"));
  await expect(page.getByTestId("footer")).toContainText(bundle.statement);
});

test("moving the budget slider changes the allocation and the expected profit", async ({ page }) => {
  await open(page, "/budget/");
  await ready(page);
  const chart = page.getByTestId("alloc-chart");
  const bars = chart.locator('[data-testid="bar"][data-series="plan"]');
  await expect(bars).toHaveCount(bundle.channels.length);
  const spends = () => bars.evaluateAll((els) => els.map((el) => el.getAttribute("data-value")));
  const before = await spends();
  const profit = page.getByTestId("expected-profit");
  await expect(profit).toContainText("$");
  const profitBefore = (await profit.textContent()) ?? "";
  const source = page.getByTestId("budget-source");
  await expect(source).toHaveText(/precomputed|live API/);

  const slider = page.getByTestId("budget-slider");
  await slider.focus();
  await page.keyboard.press("ArrowRight");

  await expect.poll(spends).not.toEqual(before);
  await expect(profit).not.toHaveText(profitBefore);
  await expect(profit).toContainText("$");
  await expect(source).toHaveText(/precomputed|live API/);
});

test("saving a plan shows its id and inputs hash from the recorded session when the API is asleep", async ({ page }) => {
  await open(page, "/budget/");
  await ready(page);
  await page.getByTestId("save-plan-button").click();
  const saved = recorded.responses.save_plan?.body;
  await expect(page.getByTestId("saved-plan-id")).toHaveText(saved?.plan_id ?? /^[0-9a-f-]{36}$/);
  await expect(page.getByTestId("saved-plan-hash")).toHaveText(saved?.plan?.inputs_hash ?? /^[0-9a-f]{16}$/);
  await expect(page.getByTestId("saved-plan")).toContainText("recorded session");
  await expect(page.getByTestId("save-source")).toHaveText("recorded session (API asleep)");
});

test("the experiments page draws the placebo chart with the truth marker, and the plan hash", async ({ page }) => {
  await open(page, "/experiments/");
  await ready(page);
  const placebo = page.getByTestId("placebo-chart");
  await expect(placebo.locator("svg[role='img'] path").first()).toBeVisible();
  await expect(placebo.locator("[data-truth-marker]")).toHaveCount(1);
  await expect(placebo.locator("[data-legend-item='truth (simulated)']")).toBeVisible();
  await expect(page.getByTestId("plan-hash")).toHaveText(printed("geo.plan_hash"));
});

test("every targeting policy has a legend entry, and every chart a table toggle that shows a table", async ({ page }) => {
  await open(page, "/targeting/");
  await ready(page);
  const policies = (manifest.tables["targeting.hillstrom.policies"]?.rows ?? []).map((row) => String(row[0]));
  expect(policies.length).toBeGreaterThan(1);
  for (const dataset of ["hillstrom", "sim", "criteo"]) {
    await page.getByTestId(`tab-${dataset}`).click();
    const panel = page.getByTestId(`panel-${dataset}`);
    for (const chart of ["qini-chart", "policy-value-chart"]) {
      const legend = panel.getByTestId(chart).getByRole("list", { name: "Legend" });
      for (const policy of policies) {
        await expect(legend.locator(`[data-legend-item="${policy}"]`), `${dataset} ${chart} ${policy}`).toBeVisible();
      }
    }
    const figures = panel.locator("figure");
    const count = await figures.count();
    expect(count, dataset).toBeGreaterThanOrEqual(2);
    for (let i = 0; i < count; i += 1) {
      const figure = figures.nth(i);
      const toggle = figure.getByTestId("table-toggle");
      await expect(figure.locator("table")).toHaveCount(0);
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await expect(figure.locator("table")).toBeVisible();
      await expect(figure.locator("table tbody tr").first()).toBeVisible();
    }
  }
});

for (const route of ROUTES) {
  test(`${route} carries the statement and the pushback, with no console errors`, async ({ page }) => {
    const errors = collectErrors(page);
    await open(page, route);
    await expect(page.getByTestId("footer")).toContainText(bundle.statement);
    await expect(page.getByRole("heading", { name: "What the CMO would push back on" })).toBeVisible();
    await ready(page);
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });
}

test("the theme toggle switches data-theme and remembers the choice", async ({ page }) => {
  await open(page, "/");
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  const after = before === "dark" ? "light" : "dark";
  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", after);
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", after);
});

test("every chart on the mix page has a table toggle", async ({ page }) => {
  await open(page, "/mix/");
  await ready(page);
  const toggles = page.getByTestId("table-toggle");
  const count = await toggles.count();
  expect(count).toBeGreaterThan(4);
  for (let i = 0; i < count; i += 1) await expect(toggles.nth(i)).toHaveAttribute("aria-pressed", "false");
});
