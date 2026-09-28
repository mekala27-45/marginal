// What the tests share: the routes, the published data the pages are checked against, and a way to
// open a page as a reader would with the live API asleep.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Page } from "@playwright/test";

export const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "/marginal";

// Every page the export writes, in navigation order.
export const ROUTES = ["/", "/mix/", "/budget/", "/experiments/", "/targeting/", "/report/"];

const data = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../../public/data/${name}`, import.meta.url)), "utf8"));

export interface ManifestFile {
  values: Record<string, { value: number | string | null; fmt: string }>;
  tables: Record<string, { columns: string[]; rows: (number | string | null)[][] }>;
}
export const manifest: ManifestFile = data("manifest.json");
export const bundle: { statement: string; channels: { key: string; label: string }[] } = data("bundle.json");
export const recorded: { responses: Record<string, { body: { plan_id?: string; plan?: { inputs_hash: string } } }> } =
  data("recorded_session.json");

/**
 * Open a route with every request that leaves the test server left hanging, the way a stopped Fly
 * machine behaves. The page's six second probe then gives up and it answers from the recorded
 * session. No test needs the network, and none can reach a live API by accident.
 */
export async function open(page: Page, route: string): Promise<void> {
  await page.route(
    (url) => url.hostname !== "127.0.0.1" && url.hostname !== "localhost",
    () => {
      // Never answered.
    },
  );
  await page.goto(`${BASE}${route}`);
}

/** The page sets data-ready on <html> once its first query over the marts has answered. */
export async function ready(page: Page): Promise<void> {
  await page.waitForFunction(() => document.documentElement.getAttribute("data-ready") === "true", null, { timeout: 45_000 });
}

/** Console errors and uncaught exceptions, collected from the moment this is called. */
export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`${msg.text()} (${msg.location().url})`);
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}
