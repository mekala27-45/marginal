import type { NextConfig } from "next";

// Static export for GitHub Pages, where the site lives under /marginal. The same base path is the
// default here so that a plain `npm run build` produces what Pages serves and what the Playwright
// tests load; set NEXT_PUBLIC_BASE_PATH to an empty string to build for the root of a domain.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/marginal";

// The live API. The workflow passes the MARGINAL_API_URL repository variable, which is empty
// until someone sets it, so an empty value falls back to the deployed address.
const api = process.env.NEXT_PUBLIC_MARGINAL_API || "https://marginal-alderquist-api.fly.dev";

const config: NextConfig = {
  output: "export",
  basePath,
  assetPrefix: basePath || undefined,
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // Inlined into both the server pass and the browser bundle, so the two always agree.
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
    NEXT_PUBLIC_MARGINAL_API: api,
  },
};

export default config;
