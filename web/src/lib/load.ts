// Build time readers for the committed bundle in public/data. Server components call these while
// the static export renders; nothing here ships to the browser.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { type Manifest, ManifestView } from "./manifest";

const DATA = join(process.cwd(), "public", "data");

function readJson<T>(name: string): T {
  return JSON.parse(readFileSync(join(DATA, name), "utf8")) as T;
}

let cached: ManifestView | null = null;
export function manifest(): ManifestView {
  if (!cached) cached = new ManifestView(readJson<Manifest>("manifest.json"));
  return cached;
}

export interface Channel {
  key: string;
  label: string;
}
export interface Bundle {
  brand: string;
  statement: string;
  channels: Channel[];
  policy: Record<string, number | string>;
  files: string[];
}

export function bundle(): Bundle {
  return readJson<Bundle>("bundle.json");
}
