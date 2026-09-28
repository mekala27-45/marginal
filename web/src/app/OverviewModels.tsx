"use client";

import { useMemo, useState } from "react";

import { ChartFrame, ChartSkeleton, type TableData } from "@/components/charts/ChartFrame";
import { Forest, type ForestRow } from "@/components/charts/Forest";
import { KpiTree, type KpiLine } from "@/components/charts/KpiTree";
import { Segmented } from "@/components/Controls";
import { CHANNELS, channel } from "@/lib/channels";
import { mart } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { useMart } from "@/lib/useMart";

export type Backend = "own" | "bayes";

export interface BackendText {
  name: string;
  kpiCallout: string;
  kpiProvenance: string;
  returnsCallout: string;
  returnsProvenance: string;
}

export interface ReturnRow extends Record<string, unknown> {
  backend: string;
  channel: string;
  channel_label: string;
  roas: number;
  roas_lower: number;
  roas_upper: number;
  roas_true: number;
  covered: boolean;
}

interface KpiRow extends Record<string, unknown> {
  series: string;
  label: string;
  backend: string;
  value: number;
  truth: number;
  first_week: number;
  last_week: number;
  weeks: number;
}

const BACKENDS: { value: Backend; label: string }[] = [
  { value: "own", label: "Own" },
  { value: "bayes", label: "Bayes" },
];

export function OverviewModels({
  text,
  initialReturns,
  breakeven,
  level,
}: {
  text: Record<Backend, BackendText>;
  initialReturns: ReturnRow[];
  breakeven: { value: number; label: string };
  /** The stated interval level, printed from the manifest. */
  level: string;
}) {
  const [backend, setBackend] = useState<Backend>("own");
  const kpi = useMart<KpiRow>(`select series, label, backend, value, truth, first_week, last_week, weeks from ${mart("kpi")}`);
  const returns = useMart<ReturnRow>(
    `select backend, channel, channel_label, roas, roas_lower, roas_upper, roas_true, covered from ${mart("returns")}`,
    initialReturns,
  );
  const t = text[backend];

  const kpiLines = useMemo((): KpiLine[] | null => {
    if (!kpi.rows) return null;
    const pick = (series: string, b: string) => kpi.rows?.find((r) => r.series === series && r.backend === b);
    const sales = pick("sales", "truth");
    const baseline = pick("baseline", backend);
    const spend = pick("spend", "truth");
    const channels = CHANNELS.map((c) => ({ c, row: pick(c.key, backend) }));
    const lines: KpiLine[] = [];
    if (sales) lines.push({ key: "sales", label: `${sales.label} (observed)`, depth: 0, value: sales.value, truth: null });
    if (baseline) lines.push({ key: "baseline", label: baseline.label, depth: 1, value: baseline.value, truth: baseline.truth });
    lines.push({
      key: "incremental",
      label: "Incremental, by channel",
      depth: 1,
      value: channels.reduce((sum, { row }) => sum + (row?.value ?? 0), 0),
      truth: channels.reduce((sum, { row }) => sum + (row?.truth ?? 0), 0),
      note: "the sum of the channel lines below",
    });
    for (const { c, row } of channels) {
      if (row) lines.push({ key: c.key, label: c.label, depth: 2, value: row.value, truth: row.truth, color: c.color });
    }
    if (spend) lines.push({ key: "spend", label: spend.label, depth: 0, value: spend.value, truth: null });
    return lines;
  }, [kpi.rows, backend]);

  const quarter = kpi.rows?.[0];
  const kpiTable: TableData | null = kpiLines
    ? {
        columns: ["Line", `${t.name} estimate`, "Truth (simulated)"],
        formats: ["text", "usd0", "usd0"],
        rows: kpiLines.map((l) => [l.label, l.value, l.truth]),
      }
    : null;

  const chosen = (returns.rows ?? [])
    .filter((r) => r.backend === backend)
    .sort((a, b) => channel(a.channel).slot - channel(b.channel).slot);
  const forestRows: ForestRow[] = chosen.map((r) => ({
    key: r.channel,
    label: r.channel_label,
    color: channel(r.channel).color,
    estimate: r.roas,
    low: r.roas_lower,
    high: r.roas_upper,
    truth: r.roas_true,
    note: r.covered ? "the interval covers the truth" : "the interval excludes the truth",
  }));
  const returnsTable: TableData = {
    columns: ["Channel", "Return", "Lower", "Upper", "Truth (simulated)", "Covers the truth"],
    formats: ["text", "float2", "float2", "float2", "float2", "text"],
    rows: chosen.map((r) => [r.channel_label, r.roas, r.roas_lower, r.roas_upper, r.roas_true, r.covered ? "yes" : "no"]),
  };

  return (
    <div className="space-y-5">
      <Segmented label="Mix model" options={BACKENDS} value={backend} onChange={setBackend} testId="backend-toggle" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ChartFrame
          title={
            quarter
              ? `The latest quarter, weeks ${formatValue(quarter.first_week, "int")} to ${formatValue(quarter.last_week, "int")}: where sales came from`
              : "The latest quarter: where sales came from"
          }
          callout={t.kpiCallout}
          provenance={t.kpiProvenance}
          table={kpiTable}
          testId="kpi-tree"
        >
          {kpiLines ? (
            <KpiTree lines={kpiLines} fmt="usdm" estimateLabel={`${t.name} estimate`} />
          ) : (
            <ChartSkeleton shape="table" rows={11} height={380} />
          )}
          {kpi.error ? <p className="text-sm text-ink2 mt-2">The quarter did not load: {kpi.error}</p> : null}
        </ChartFrame>
        <ChartFrame
          title={`Return on ad spend by channel, ${t.name.toLowerCase()} model, with its interval and the truth`}
          callout={t.returnsCallout}
          provenance={t.returnsProvenance}
          table={returnsTable}
          testId="returns-forest"
        >
          <Forest
            rows={forestRows}
            fmt="float2"
            axisLabel="Revenue per dollar of spend"
            reference={breakeven}
            intervalLabel={`with its ${level} interval`}
          />
        </ChartFrame>
      </div>
    </div>
  );
}
