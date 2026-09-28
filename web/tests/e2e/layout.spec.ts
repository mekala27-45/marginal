import { expect, test } from "@playwright/test";

import { open, ready, ROUTES } from "./site";

// At phone width no page may scroll sideways; wide tables scroll inside their own region.
for (const route of ROUTES) {
  test(`${route} has no horizontal page scroll at phone width`, async ({ page }) => {
    await open(page, route);
    await ready(page);
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("the budget page stacks the slider above the allocation on a phone", async ({ page }) => {
  await open(page, "/budget/");
  await ready(page);
  const slider = await page.getByTestId("budget-slider").boundingBox();
  const chart = await page.getByTestId("alloc-chart").boundingBox();
  expect(slider && chart && slider.y < chart.y).toBe(true);
});
