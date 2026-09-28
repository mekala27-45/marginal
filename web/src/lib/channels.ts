// The seven channels in their fixed order, one categorical slot each, the same on every page.
// Slot eight belongs to the "everyone" and "random" comparators and never to a channel.
import bundleJson from "../../public/data/bundle.json";

export interface ChannelInfo {
  key: string;
  label: string;
  /** One word, for axes too narrow for the full name. */
  short: string;
  slot: number;
  color: string;
}

const SHORT: Record<string, string> = {
  paid_search: "Search",
  paid_social: "Social",
  online_video: "Video",
  display_retargeting: "Display",
  email: "Email",
  affiliate_promo: "Affiliate",
  direct_mail: "Mail",
};

export const CHANNELS: ChannelInfo[] = bundleJson.channels.map((c, i) => ({
  key: c.key,
  label: c.label,
  short: SHORT[c.key] ?? c.label,
  slot: i + 1,
  color: `var(--cat-${i + 1})`,
}));

export const CHANNEL_KEYS = CHANNELS.map((c) => c.key);

const byKey = new Map(CHANNELS.map((c) => [c.key, c]));
const byLabel = new Map(CHANNELS.map((c) => [c.label, c]));

export function channel(keyOrLabel: string): ChannelInfo {
  const hit = byKey.get(keyOrLabel) ?? byLabel.get(keyOrLabel);
  if (!hit) throw new Error(`unknown channel ${keyOrLabel}`);
  return hit;
}

/** The comparator slot, for "everyone" and the random diagonal. */
export const COMPARATOR = "var(--cat-8)";

export const STATEMENT: string = bundleJson.statement;
export const BRAND: string = bundleJson.brand;
