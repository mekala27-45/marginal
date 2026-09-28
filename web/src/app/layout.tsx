import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/public-sans/index.css";
import "@fontsource-variable/red-hat-mono/index.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { THEME_SCRIPT } from "@/components/ThemeToggle";
import palette from "@/theme/palette.json";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "marginal: the quarterly marketing review", template: "%s | marginal" },
  description:
    "Marketing measurement for Alderquist, a fictional brand in a simulated market with known truth: mix models graded on that truth, a lift test that corrects them, and a budget judged at the margin.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: palette.light.surface },
    { media: "(prefers-color-scheme: dark)", color: palette.dark.surface },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The theme script sets data-theme before first paint, so the server markup cannot match it.
    <html lang="en" suppressHydrationWarning>
      <body>
        {/* First in the body, so it runs before anything paints. An explicit <head> in this layout
            let React's hydration cursor stray into the head when script chunks arrived late. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
