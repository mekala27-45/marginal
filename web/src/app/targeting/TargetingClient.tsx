"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useState } from "react";

import { ChartFrame, ChartSkeleton, type TableData } from "@/components/charts/ChartFrame";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart, type LineSeries, type PointMark } from "@/components/charts/LineChart";
import { Passed, Status } from "@/components/Status";
import { COMPARATOR } from "@/lib/channels";
import { mart } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { useMart } from "@/lib/useMart";

export type Dataset = "hillstrom" | "sim" | "criteo";
type Panel = { callout: string; provenance: string };

export interface DatasetText {
  tab: string;
  qiniUnit: string;
  qini: Panel;
  value: Panel & { costs: string; fmt: string; unit: string };
  summaryProvenance: string;
  /** A plain statement that belongs to this dataset, shown above its charts. */
  lead: string;
}
export interface TargetingText {
  level: string;
  datasets: Record<Dataset, DatasetText>;
  quadrants: Panel & { labels: Record<string, string> };
}

// One color per policy, the same on every tab: the lead slots for the learners and the rule, slot
// eight for the comparators (everyone, and the random diagonal), each with its own dash as well.
const POLICY_STYLE: Record<string, { color: string; dash?: string }> = {
  t_learner: { color: "var(--cat-1)" },
  x_learner: { color: "var(--cat-3)", dash: "9 3 2 3" },
  sure_things: { color: "var(--cat-2)", dash: "2 3" },
  everyone: { color: COMPARATOR, dash: "7 3" },
};
const ORDER = ["t_learner", "x_learner", "sure_things", "everyone"];
const DATASETS: Dataset[] = ["hillstrom", "sim", "criteo"];

interface QiniRow extends Record<string, unknown> {
  dataset: string;
  policy: string;
  policy_label: string;
  share: number;
  qini: number;
  qini_lower: number;
  qini_upper: number;
  random: number;
}
interface ValueRow extends Record<string, unknown> {
  dataset: string;
  policy: string;
  policy_label: string;
  split: string;
  share: number;
  profit_per_thousand: number;
}
interface SummaryRow extends Record<string, unknown> {
  dataset: string;
  policy: string;
  policy_label: string;
  chosen_share: number;
  interior: boolean;
  interior_reason: string;
  qini: number;
  qini_lower: number;
  qini_upper: number;
  top_decile_uplift: number;
  profit_per_thousand_test: number;
  profit_per_thousand_validation: number;
}
interface QuadrantRow extends Record<string, unknown> {
  policy: string;
  policy_label: string;
  quadrant: string;
  share_of_quadrant_contacted: number;
}

export function TargetingClient({ text, extra }: { text: TargetingText; extra: Record<Dataset, ReactNode> }) {
  const [tab, setTab] = useState<Dataset>("hillstrom");
  const qini = useMart<QiniRow>(
    `select dataset, policy, policy_label, share, qini, qini_lower, qini_upper, random from ${mart("qini")} order by dataset, policy, share`,
  );
  const value = useMart<ValueRow>(
    `select dataset, policy, policy_label, split, share, profit_per_thousand from ${mart("policy_value")} order by dataset, policy, split, share`,
  );
  const summary = useMart<SummaryRow>(
    `select dataset, policy, policy_label, chosen_share, interior, interior_reason, qini, qini_lower, qini_upper, top_decile_uplift, profit_per_thousand_test, profit_per_thousand_validation from ${mart("targeting_summary")}`,
  );

  // The tab is part of the address, so a link can open the Criteo view directly.
  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (DATASETS.includes(hash as Dataset)) setTab(hash as Dataset);
  }, []);
  const choose = (d: Dataset) => {
    setTab(d);
    try {
      window.history.replaceState(null, "", `#${d}`);
    } catch {
      // Some embedded browsers refuse history edits; the tab still changes.
    }
  };
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = DATASETS.indexOf(tab);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = DATASETS[(i + (e.key === "ArrowRight" ? 1 : DATASETS.length - 1)) % DATASETS.length] ?? "hillstrom";
      choose(next);
      document.getElementById(`tab-${next}`)?.focus();
    }
  };

  const t = text.datasets[tab];
  return (
    <div>
      <div role="tablist" aria-label="Dataset" className="flex flex-wrap gap-1 border-b border-hairline mb-6">
        {DATASETS.map((d) => (
          <button
            key={d}
            id={`tab-${d}`}
            role="tab"
            type="button"
            aria-selected={tab === d}
            aria-controls={`panel-${d}`}
            tabIndex={tab === d ? 0 : -1}
            onClick={() => choose(d)}
            onKeyDown={onKey}
            className={`px-3 py-2 text-sm -mb-px border-b-2 ${tab === d ? "border-lead text-ink font-semibold" : "border-transparent text-ink2 hover:text-ink"}`}
            data-testid={`tab-${d}`}
          >
            {text.datasets[d].tab}
          </button>
        ))}
      </div>
      {/* Keyed by dataset: each tab opens on its charts, whatever was toggled on the last one. */}
      <div key={tab} role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} data-testid={`panel-${tab}`}>
        <p className="prose mb-5 text-[1.02rem] leading-relaxed" data-testid="dataset-lead">
          {t.lead}
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Qini dataset={tab} rows={qini.rows} text={t} />
          <PolicyValue dataset={tab} rows={value.rows} summary={summary.rows} text={t} />
        </div>
        <Summary dataset={tab} rows={summary.rows} text={t} level={text.level} />
        {tab === "sim" ? <Quadrants text={text} /> : null}
        {extra[tab]}
      </div>
    </div>
  );
}

function Qini({ dataset, rows, text }: { dataset: Dataset; rows: QiniRow[] | null; text: DatasetText }) {
  const mine = useMemo(() => (rows ?? []).filter((r) => r.dataset === dataset), [rows, dataset]);
  const policies = ORDER.filter((p) => mine.some((r) => r.policy === p));
  const label = (p: string) => mine.find((r) => r.policy === p)?.policy_label ?? p;
  const series: LineSeries[] = [
    ...policies.map((p) => {
      const pts = mine.filter((r) => r.policy === p);
      return {
        key: p,
        name: label(p),
        color: POLICY_STYLE[p]?.color ?? "var(--ink)",
        dash: POLICY_STYLE[p]?.dash,
        points: pts.map((r) => ({ x: r.share, y: r.qini })),
        band: p === "everyone" ? undefined : pts.map((r) => ({ x: r.share, low: r.qini_lower, high: r.qini_upper })),
      };
    }),
  ];
  const randomPts = mine.filter((r) => r.policy === policies[0]).map((r) => ({ x: r.share, y: r.random }));
  if (randomPts.length)
    series.push({ key: "random", name: "random targeting", color: COMPARATOR, dash: "2 2", width: 1.5, points: randomPts, label: false });
  const table: TableData | null = rows
    ? {
        columns: ["Policy", "Share contacted", "Qini", "Lower", "Upper", "Random"],
        formats: ["text", "pct0", "float2", "float2", "float2", "float2"],
        rows: mine
          .filter((r) => Math.round(r.share * 100) % 5 === 0)
          .map((r) => [r.policy_label, r.share, r.qini, r.qini_lower, r.qini_upper, r.random]),
      }
    : null;
  return (
    <ChartFrame
      title="Qini curves: who the model contacts first, against random targeting"
      callout={text.qini.callout}
      provenance={text.qini.provenance}
      table={table}
      testId="qini-chart"
    >
      {rows ? (
        <LineChart
          series={series}
          xFmt="pct0"
          yFmt="float1"
          xLabel="Share of the list contacted, best first"
          yLabel={text.qiniUnit}
          height={300}
        />
      ) : (
        <ChartSkeleton shape="lines" height={300} />
      )}
    </ChartFrame>
  );
}

function PolicyValue({
  dataset,
  rows,
  summary,
  text,
}: {
  dataset: Dataset;
  rows: ValueRow[] | null;
  summary: SummaryRow[] | null;
  text: DatasetText;
}) {
  const mine = useMemo(() => (rows ?? []).filter((r) => r.dataset === dataset), [rows, dataset]);
  const chosen = (summary ?? []).filter((s) => s.dataset === dataset);
  const policies = ORDER.filter((p) => mine.some((r) => r.policy === p));
  const label = (p: string) => mine.find((r) => r.policy === p)?.policy_label ?? p;
  const series: LineSeries[] = policies.flatMap((p) => {
    const style = POLICY_STYLE[p] ?? { color: "var(--ink)" };
    const pts = (split: string) =>
      mine.filter((r) => r.policy === p && r.split === split).map((r) => ({ x: r.share, y: r.profit_per_thousand }));
    return [
      { key: `${p}-test`, name: label(p), color: style.color, dash: style.dash, points: pts("test") },
      {
        key: `${p}-validation`,
        name: `${label(p)}, validation`,
        color: style.color,
        dash: "1 3",
        opacity: 0.55,
        width: 1.5,
        points: pts("validation"),
        legend: false,
      },
    ];
  });
  const marks: PointMark[] = chosen
    .filter((s) => policies.includes(s.policy))
    .map((s) => {
      const hit = mine.find((r) => r.policy === s.policy && r.split === "test" && Math.abs(r.share - s.chosen_share) < 1e-9);
      return hit
        ? {
            x: s.chosen_share,
            y: hit.profit_per_thousand,
            label: `${s.policy_label} chosen share`,
            color: POLICY_STYLE[s.policy]?.color ?? "var(--ink)",
          }
        : null;
    })
    .filter((m): m is PointMark => m !== null);
  const table: TableData | null = rows
    ? {
        columns: ["Policy", "Split", "Share contacted", text.value.unit],
        formats: ["text", "text", "pct0", text.value.fmt],
        rows: mine.map((r) => [r.policy_label, r.split, r.share, r.profit_per_thousand]),
      }
    : null;
  return (
    <ChartFrame
      title="Policy value by share contacted, test split, with the share chosen on validation marked"
      callout={
        <>
          {text.value.callout} <span className="text-ink2">{text.value.costs}</span>
        </>
      }
      provenance={text.value.provenance}
      table={table}
      testId="policy-value-chart"
    >
      {rows && summary ? (
        <LineChart
          series={series}
          marks={marks}
          xFmt="pct0"
          yFmt={text.value.fmt}
          xLabel="Share of the list contacted"
          yLabel={text.value.unit}
          height={300}
          extraLegend={[
            { label: "validation split, lighter", color: "var(--ink2)", kind: "line", dash: "1 3", opacity: 0.55 },
            { label: "the share chosen on validation", color: "var(--ink2)", kind: "dot" },
          ]}
        />
      ) : (
        <ChartSkeleton shape="lines" height={300} />
      )}
    </ChartFrame>
  );
}

function Summary({ dataset, rows, text, level }: { dataset: Dataset; rows: SummaryRow[] | null; text: DatasetText; level: string }) {
  const mine = ORDER.map((p) => (rows ?? []).find((r) => r.dataset === dataset && r.policy === p)).filter((r): r is SummaryRow =>
    Boolean(r),
  );
  return (
    <div className="card p-4 sm:p-5 mt-5" data-testid="targeting-summary">
      <h3 className="font-sans text-[0.95rem] font-semibold mb-3">Each policy on the test split</h3>
      {rows ? (
        <div className="overflow-x-auto" role="region" aria-label="Policy summary" tabIndex={0}>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Policy</th>
                <th scope="col" className="num">
                  Qini coefficient
                </th>
                <th scope="col" className="num">
                  {level} interval
                </th>
                <th scope="col" className="num">
                  Top decile uplift
                </th>
                <th scope="col" className="num">
                  Chosen share
                </th>
                <th scope="col">Operating point</th>
                <th scope="col" className="num">
                  Value on test
                </th>
              </tr>
            </thead>
            <tbody>
              {mine.map((r) => (
                <tr key={r.policy}>
                  <td>{r.policy_label}</td>
                  <td className="num">{formatValue(r.qini, "float3")}</td>
                  <td className="num">
                    {formatValue(r.qini_lower, "float3")} to {formatValue(r.qini_upper, "float3")}
                  </td>
                  <td className="num">{formatValue(r.top_decile_uplift, "pct2")}</td>
                  <td className="num">{formatValue(r.chosen_share, "pct0")}</td>
                  <td className="min-w-[14rem]">
                    {r.policy === "everyone" ? (
                      <span className="text-ink2">the baseline, by definition</span>
                    ) : r.interior ? (
                      <Passed>interior</Passed>
                    ) : (
                      <Status kind="warning">degenerate operating point</Status>
                    )}
                    <span className="block text-xs text-ink2">{r.interior_reason}</span>
                  </td>
                  <td className="num">{formatValue(r.profit_per_thousand_test, text.value.fmt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ChartSkeleton shape="table" rows={4} height={160} />
      )}
      <p className="text-xs text-ink2 mt-3">
        Value on test is {text.value.unit}. {text.summaryProvenance}
      </p>
    </div>
  );
}

function Quadrants({ text }: { text: TargetingText }) {
  const { rows } = useMart<QuadrantRow>(`select policy, policy_label, quadrant, share_of_quadrant_contacted from ${mart("quadrants")}`);
  const policies = [...ORDER, "oracle"].filter((p) => (rows ?? []).some((r) => r.policy === p));
  const quadrants = [...new Set((rows ?? []).map((r) => r.quadrant))];
  const labelOf = (p: string) => (p === "oracle" ? "Oracle, for reference" : ((rows ?? []).find((r) => r.policy === p)?.policy_label ?? p));
  const cells = policies.map((p) =>
    quadrants.map((q) => (rows ?? []).find((r) => r.policy === p && r.quadrant === q)?.share_of_quadrant_contacted ?? null),
  );
  const table: TableData | null = rows
    ? {
        columns: ["Policy", ...quadrants.map((q) => text.quadrants.labels[q] ?? q)],
        formats: ["text", ...quadrants.map(() => "pct1")],
        rows: policies.map((p, i) => [labelOf(p), ...(cells[i] ?? [])]),
      }
    : null;
  return (
    <div className="mt-5">
      <ChartFrame
        title="Share of each true quadrant that each policy contacts"
        callout={text.quadrants.callout}
        provenance={text.quadrants.provenance}
        table={table}
        testId="quadrant-chart"
      >
        {rows ? (
          <Heatmap
            rows={policies.map(labelOf)}
            columns={quadrants.map((q) => text.quadrants.labels[q] ?? q)}
            cells={cells}
            fmt="pct0"
            rowLabel="policy"
            columnLabel="True quadrant, known because the customers are simulated"
          />
        ) : (
          <ChartSkeleton shape="table" rows={5} height={220} />
        )}
      </ChartFrame>
    </div>
  );
}
