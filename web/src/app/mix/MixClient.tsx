"use client";

import { type ReactNode, useMemo, useState } from "react";

import { ChartFrame, ChartSkeleton, type TableData } from "@/components/charts/ChartFrame";
import { PATTERN } from "@/components/charts/Defs";
import { Forest } from "@/components/charts/Forest";
import { GroupedBars } from "@/components/charts/GroupedBars";
import { IntervalColumns } from "@/components/charts/IntervalColumns";
import { Legend } from "@/components/charts/Legend";
import { LineChart } from "@/components/charts/LineChart";
import { StackedArea, type StackLayer } from "@/components/charts/StackedArea";
import { Segmented } from "@/components/Controls";
import { Passed, Status } from "@/components/Status";
import { CHANNELS, channel } from "@/lib/channels";
import { mart } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { useMart } from "@/lib/useMart";

export type Backend = "own" | "bayes";
type Panel = { callout: string; provenance: string };

export interface ReturnRow extends Record<string, unknown> {
  backend: string;
  channel: string;
  channel_label: string;
  roas: number;
  roas_lower: number;
  roas_upper: number;
  roas_true: number;
  covered: boolean;
  marginal_return: number;
  marginal_true: number;
}

export interface MixText {
  name: Record<Backend, string>;
  level: string;
  contributions: Record<Backend, Panel>;
  returns: Record<Backend, { intro: string; provenance: string }>;
  crosscheck: { intro: string; provenance: string };
  curves: Record<Backend, Panel>;
  halfLives: Record<Backend, Panel>;
  recovery: {
    callout: string;
    provenance: Record<Backend, string>;
    tables: Record<Backend, TableData>;
    floor: number;
    floorLabel: string;
    demonstration: string;
    conditions: string;
    seeds: string;
  };
  attribution: Panel & { table: TableData };
  initialReturns: ReturnRow[];
}

const BACKENDS: { value: Backend; label: string }[] = [
  { value: "own", label: "Own" },
  { value: "bayes", label: "Bayes" },
];

export function MixClient({ text }: { text: MixText }) {
  const [backend, setBackend] = useState<Backend>("own");
  return (
    <div className="space-y-12">
      <div className="sticky top-0 z-20 -mx-4 px-4 sm:-mx-6 sm:px-6 py-2 bg-surface border-b border-hairline">
        <Segmented label="Mix model on every panel" options={BACKENDS} value={backend} onChange={setBackend} testId="backend-toggle" />
      </div>
      <Contributions backend={backend} text={text} />
      <Returns backend={backend} text={text} />
      <Curves backend={backend} text={text} />
      <Recovery backend={backend} text={text} />
      <Attribution text={text} />
    </div>
  );
}

function Heading({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-4">
      <h2 className="text-[1.6rem] leading-tight">{title}</h2>
      {children ? <div className="prose text-ink2 mt-2 space-y-2">{children}</div> : null}
    </div>
  );
}

interface ContributionRow extends Record<string, unknown> {
  week: number;
  backend: string;
  baseline: number;
  sales: number;
}

function Contributions({ backend, text }: { backend: Backend; text: MixText }) {
  const cols = ["week", "backend", "baseline", ...CHANNELS.map((c) => c.key), "sales", "fitted"].join(", ");
  const { rows, error } = useMart<ContributionRow>(`select ${cols} from ${mart("contributions")} order by backend, week`);
  const mine = useMemo(() => (rows ?? []).filter((r) => r.backend === backend), [rows, backend]);
  const layers: StackLayer[] = [
    { key: "baseline", label: "Baseline", color: "var(--chart-bg)", pattern: PATTERN.baseline },
    ...CHANNELS.map((c) => ({ key: c.key, label: c.label, color: c.color })),
  ];
  const table: TableData | null = rows
    ? {
        columns: ["Week", "Baseline", ...CHANNELS.map((c) => c.label), "Sales"],
        formats: ["int", "usd0", ...CHANNELS.map(() => "usd0"), "usd0"],
        rows: mine.map((r) => [r.week, r.baseline, ...CHANNELS.map((c) => r[c.key] as number), r.sales]),
      }
    : null;
  return (
    <section aria-label="Contributions over time">
      <Heading title="Where weekly sales came from" />
      <ChartFrame
        title={`Weekly sales split into the baseline and each channel, ${text.name[backend].toLowerCase()} model`}
        callout={text.contributions[backend].callout}
        provenance={text.contributions[backend].provenance}
        table={table}
        testId="contributions"
      >
        {rows ? (
          <StackedArea
            rows={mine.map((r) => ({
              x: r.week,
              values: Object.fromEntries(layers.map((l) => [l.key, Number(r[l.key] ?? 0)])),
              total: r.sales,
            }))}
            layers={layers}
            totalLabel="Sales (observed)"
            xFmt="int"
            yFmt="usdm"
            xLabel="Week"
            yLabel="Weekly sales"
            height={340}
          />
        ) : (
          <ChartSkeleton shape="area" height={340} />
        )}
        {error ? <p className="text-sm text-ink2">The contributions did not load: {error}</p> : null}
      </ChartFrame>
    </section>
  );
}

interface CrossRow extends Record<string, unknown> {
  channel: string;
  channel_label: string;
  own: number;
  own_lower: number;
  own_upper: number;
  truth: number;
  bayes: number;
  bayes_lower: number;
  bayes_upper: number;
  disagree: boolean;
}

function Returns({ backend, text }: { backend: Backend; text: MixText }) {
  const returns = useMart<ReturnRow>(
    `select backend, channel, channel_label, roas, roas_lower, roas_upper, roas_true, covered, marginal_return, marginal_true from ${mart("returns")}`,
    text.initialReturns,
  );
  const cross = useMart<CrossRow>(`select * from ${mart("crosscheck")}`);
  const mine = (returns.rows ?? []).filter((r) => r.backend === backend).sort((a, b) => channel(a.channel).slot - channel(b.channel).slot);
  const f2 = (v: number) => formatValue(v, "float2");
  const disagreements = (cross.rows ?? []).filter((r) => r.disagree).length;
  return (
    <section aria-label="Returns and the cross check" className="space-y-10">
      <div>
        <Heading title="Return per channel against the truth">
          <p>{text.returns[backend].intro}</p>
        </Heading>
        <div className="card p-4 overflow-x-auto" role="region" aria-label="Return per channel" tabIndex={0}>
          <table className="data-table" data-testid="returns-table">
            <thead>
              <tr>
                <th scope="col">Channel</th>
                <th scope="col" className="num">
                  Return
                </th>
                <th scope="col" className="num">
                  {text.level} interval
                </th>
                <th scope="col" className="num">
                  Truth (simulated)
                </th>
                <th scope="col">Coverage</th>
                <th scope="col" className="num">
                  Marginal
                </th>
                <th scope="col" className="num">
                  True marginal
                </th>
              </tr>
            </thead>
            <tbody>
              {mine.map((r) => (
                <tr key={r.channel}>
                  <td>{r.channel_label}</td>
                  <td className="num">{f2(r.roas)}</td>
                  <td className="num">
                    {f2(r.roas_lower)} to {f2(r.roas_upper)}
                  </td>
                  <td className="num">{f2(r.roas_true)}</td>
                  <td className="whitespace-nowrap">
                    {r.covered ? <Passed>covers the truth</Passed> : <Status kind="serious">interval excludes the truth</Status>}
                  </td>
                  <td className="num">{f2(r.marginal_return)}</td>
                  <td className="num">{f2(r.marginal_true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-ink2 mt-3">{text.returns[backend].provenance}</p>
        </div>
      </div>
      <div>
        <Heading title="Own beside Bayes beside the truth">
          <p>
            {text.crosscheck.intro}{" "}
            {cross.rows
              ? disagreements === 0
                ? "On this market no channel's estimates disagree beyond their intervals."
                : `${formatValue(disagreements, "int")} channels disagree beyond their intervals and are marked.`
              : ""}
          </p>
        </Heading>
        <div className="card p-4 overflow-x-auto" role="region" aria-label="Cross check" tabIndex={0}>
          {cross.rows ? (
            <table className="data-table" data-testid="crosscheck-table">
              <thead>
                <tr>
                  <th scope="col">Channel</th>
                  <th scope="col" className="num">
                    Own
                  </th>
                  <th scope="col" className="num">
                    Bayes
                  </th>
                  <th scope="col" className="num">
                    Truth (simulated)
                  </th>
                  <th scope="col">Own against Bayes</th>
                </tr>
              </thead>
              <tbody>
                {[...cross.rows]
                  .sort((a, b) => channel(a.channel).slot - channel(b.channel).slot)
                  .map((r) => (
                    <tr key={r.channel} data-status={r.disagree ? "warning" : undefined}>
                      <td>{r.channel_label}</td>
                      <td className="num">
                        {f2(r.own)}
                        <span className="block text-xs text-ink2">
                          {f2(r.own_lower)} to {f2(r.own_upper)}
                        </span>
                      </td>
                      <td className="num">
                        {f2(r.bayes)}
                        <span className="block text-xs text-ink2">
                          {f2(r.bayes_lower)} to {f2(r.bayes_upper)}
                        </span>
                      </td>
                      <td className="num">{f2(r.truth)}</td>
                      <td className="whitespace-nowrap">
                        {r.disagree ? <Status kind="warning">disagree beyond their intervals</Status> : <Passed>intervals overlap</Passed>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : (
            <ChartSkeleton shape="table" rows={7} height={300} />
          )}
          <p className="text-xs text-ink2 mt-3">{text.crosscheck.provenance}</p>
        </div>
      </div>
    </section>
  );
}

interface CurveRow extends Record<string, unknown> {
  backend: string;
  channel: string;
  spend: number;
  estimate: number;
  truth: number;
}
interface SpendRow extends Record<string, unknown> {
  channel: string;
  spend_current: number;
  marginal_own: number;
  marginal_bayes: number;
  marginal_true: number;
  half_life_own: number;
  half_life_bayes: number;
  half_life_true: number;
}

function Curves({ backend, text }: { backend: Backend; text: MixText }) {
  const curves = useMart<CurveRow>(
    `select backend, channel, spend, estimate, truth from ${mart("curves")} order by backend, channel, spend`,
  );
  const spend = useMart<SpendRow>(`select * from ${mart("current_spend")}`);
  const name = text.name[backend].toLowerCase();
  const mine = (curves.rows ?? []).filter((r) => r.backend === backend);
  const current = new Map((spend.rows ?? []).map((r) => [r.channel, r]));
  const marginal = (r: SpendRow | undefined) => (r ? (backend === "own" ? r.marginal_own : r.marginal_bayes) : null);
  const halfLife = (r: SpendRow | undefined) => (r ? (backend === "own" ? r.half_life_own : r.half_life_bayes) : null);
  const curveTable: TableData | null = curves.rows
    ? {
        columns: ["Channel", "Weekly spend", `Incremental revenue, ${name} model`, "Truth (simulated)"],
        formats: ["text", "usd0", "usd0", "usd0"],
        rows: mine.map((r) => [channel(r.channel).label, r.spend, r.estimate, r.truth]),
      }
    : null;
  const halfTable: TableData | null = spend.rows
    ? {
        columns: ["Channel", `Half life, ${name} model (weeks)`, "Truth (simulated)"],
        formats: ["text", "float1", "float1"],
        rows: CHANNELS.map((c) => [c.label, halfLife(current.get(c.key)), current.get(c.key)?.half_life_true ?? null]),
      }
    : null;
  return (
    <section aria-label="Response curves and carryover">
      <Heading title="What the next dollar earns in each channel" />
      <div className="space-y-5">
        <ChartFrame
          title={`Response curves at weekly spend, ${name} model against the truth`}
          callout={text.curves[backend].callout}
          provenance={text.curves[backend].provenance}
          table={curveTable}
          testId="curves"
        >
          <Legend
            items={[
              { label: `${text.name[backend]} model`, color: "var(--ink2)", kind: "line" },
              { label: "truth curve (simulated)", color: "var(--ink)", kind: "line", dash: "5 3" },
              { label: "truth (simulated), at current spend", color: "var(--ink)", kind: "diamond" },
              { label: "current weekly spend", color: "var(--control)", kind: "rule", dash: "2 2" },
            ]}
          />
          {curves.rows && spend.rows ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-5 gap-y-6 mt-4">
              {CHANNELS.map((c) => {
                const pts = mine.filter((r) => r.channel === c.key);
                const now = current.get(c.key);
                // The curve grid includes current spend itself, so both marks sit on a published point.
                const at = now
                  ? pts.find((p) => Math.abs(p.spend - now.spend_current) <= 1e-6 * Math.max(1, now.spend_current))
                  : undefined;
                return (
                  <div key={c.key} data-curve={c.key}>
                    <p className="text-[12.5px] font-semibold flex items-center gap-2">
                      <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: c.color }} aria-hidden="true" />
                      {c.label}
                    </p>
                    <LineChart
                      series={[
                        {
                          key: "estimate",
                          name: `${text.name[backend]} model`,
                          color: c.color,
                          points: pts.map((p) => ({ x: p.spend, y: p.estimate })),
                        },
                        {
                          key: "truth",
                          name: "truth (simulated)",
                          color: "var(--ink)",
                          dash: "5 3",
                          points: pts.map((p) => ({ x: p.spend, y: p.truth })),
                        },
                      ]}
                      vRules={now ? [{ x: now.spend_current, label: "now", color: "var(--control)", dash: "2 2" }] : []}
                      marks={
                        at
                          ? [
                              { x: at.spend, y: at.estimate, label: "estimate at current spend", color: c.color },
                              { x: at.spend, y: at.truth, label: "truth (simulated)", color: "var(--ink)", shape: "diamond" },
                            ]
                          : []
                      }
                      xFmt="usd0"
                      yFmt="usd0"
                      xLabel="Weekly spend"
                      yLabel="Incremental revenue"
                      height={190}
                      compact
                      showLegend={false}
                    />
                    <p className="text-xs text-ink2 mt-1">
                      Marginal return at current spend: <span className="num text-ink">{formatValue(marginal(now), "float2")}</span>, truth{" "}
                      <span className="num text-ink">{formatValue(now?.marginal_true ?? null, "float2")}</span>
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <ChartSkeleton shape="grid" rows={6} height={380} />
          )}
        </ChartFrame>
        <ChartFrame
          title={`How long a week of spend keeps working: half lives, ${name} model against the truth`}
          callout={text.halfLives[backend].callout}
          provenance={text.halfLives[backend].provenance}
          table={halfTable}
          testId="half-lives"
        >
          {spend.rows ? (
            <Forest
              rows={CHANNELS.map((c) => ({
                key: c.key,
                label: c.label,
                color: c.color,
                estimate: halfLife(current.get(c.key)),
                truth: current.get(c.key)?.half_life_true ?? null,
              }))}
              fmt="float1"
              axisLabel="Carryover half life, weeks"
              estimateLabel={`${text.name[backend]} model`}
            />
          ) : (
            <ChartSkeleton shape="forest" rows={7} height={280} />
          )}
        </ChartFrame>
      </div>
    </section>
  );
}

type Metric = "bias" | "median_abs_error" | "coverage";
interface RecoveryRow extends Record<string, unknown> {
  backend: string;
  condition: string;
  rho: number;
  feedback: boolean;
  channel: string;
  bias: number | null;
  bias_lower: number | null;
  bias_upper: number | null;
  median_abs_error: number | null;
  median_abs_error_lower: number | null;
  median_abs_error_upper: number | null;
  coverage: number | null;
  coverage_lower: number | null;
  coverage_upper: number | null;
  nominal_coverage: number;
}
interface RankRow extends Record<string, unknown> {
  backend: string;
  condition: string;
  rank_agreement: number;
  lower: number;
  upper: number;
}

const METRICS: { value: Metric; label: string; fmt: string }[] = [
  { value: "bias", label: "Bias", fmt: "spct1" },
  { value: "median_abs_error", label: "Median absolute error", fmt: "pct0" },
  { value: "coverage", label: "Coverage", fmt: "pct0" },
];

function Recovery({ backend, text }: { backend: Backend; text: MixText }) {
  const [metric, setMetric] = useState<Metric>("median_abs_error");
  const rec = useMart<RecoveryRow>(`select * from ${mart("recovery")} order by backend, feedback, rho`);
  const ranks = useMart<RankRow>(`select backend, condition, rank_agreement, lower, upper from ${mart("recovery_ranks")}`);
  const m = METRICS.find((x) => x.value === metric) ?? METRICS[1]!;
  const rows = rec.rows ?? [];
  const conditions = [...new Set(rows.filter((r) => r.backend === backend).map((r) => r.condition))];
  // One y axis for every panel and both backends, so a panel can be compared with any other.
  const domain = useMemo((): [number, number] => {
    const vals = rows
      .filter((r) => r.channel !== "all")
      .flatMap((r) => [r[metric], r[`${metric}_lower`], r[`${metric}_upper`]])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (metric === "coverage") return [0, 1];
    const lo = Math.min(0, ...vals);
    const hi = Math.max(0, ...vals);
    return [lo, hi];
  }, [rows, metric]);
  const nominal = rows[0]?.nominal_coverage ?? null;
  const reference =
    metric === "bias"
      ? { y: 0, label: "no bias" }
      : metric === "coverage"
        ? { y: nominal ?? 0, label: `nominal ${formatValue(nominal, "pct0")}` }
        : { y: text.recovery.floor, label: text.recovery.floorLabel };
  return (
    <section aria-label="The recovery study">
      <Heading title="Would the model find the truth on a market it has not seen?">
        <p>
          The simulator draws new markets with known returns under {text.recovery.conditions} conditions: how strongly spend in one channel
          moves with spend in the others (rho), and whether spend responds to last week&apos;s sales (feedback). Each backend is refit on
          every draw, {text.recovery.seeds}, and graded against the truth.
        </p>
      </Heading>
      <ChartFrame
        title={`Recovery of each channel's return across simulated markets, ${text.name[backend].toLowerCase()} model`}
        callout={text.recovery.callout}
        provenance={text.recovery.provenance[backend]}
        table={text.recovery.tables[backend]}
        testId="recovery"
        controls={
          <Segmented
            label="Measure"
            options={METRICS.map(({ value, label }) => ({ value, label }))}
            value={metric}
            onChange={setMetric}
            testId="recovery-metric"
          />
        }
      >
        <Legend
          items={[
            { label: "across seeds, with its interval", color: "var(--ink2)", kind: "interval" },
            { label: reference.label, color: "var(--ink2)", kind: "line", dash: metric === "bias" ? undefined : "4 3" },
          ]}
        />
        {rec.rows && ranks.rows ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-5 mt-4">
            {conditions.map((cond) => {
              const here = rows.filter((r) => r.backend === backend && r.condition === cond);
              const all = here.find((r) => r.channel === "all");
              const rank = ranks.rows?.find((r) => r.backend === backend && r.condition === cond);
              return (
                <IntervalColumns
                  key={cond}
                  title={cond === text.recovery.demonstration ? `${cond} (the demonstration market)` : cond}
                  subtitle={[
                    all && all[metric] !== null ? `all channels ${formatValue(all[metric], m.fmt)}` : "",
                    rank
                      ? `rank agreement ${formatValue(rank.rank_agreement, "float2")} (${formatValue(rank.lower, "float2")} to ${formatValue(rank.upper, "float2")})`
                      : "",
                  ]
                    .filter(Boolean)
                    .join("; ")}
                  points={CHANNELS.map((c) => {
                    const r = here.find((x) => x.channel === c.key);
                    return {
                      key: c.key,
                      short: c.short,
                      label: c.label,
                      color: c.color,
                      value: (r?.[metric] as number | null) ?? null,
                      low: (r?.[`${metric}_lower`] as number | null) ?? null,
                      high: (r?.[`${metric}_upper`] as number | null) ?? null,
                    };
                  })}
                  fmt={m.fmt}
                  yDomain={domain}
                  reference={reference}
                />
              );
            })}
          </div>
        ) : (
          <ChartSkeleton shape="grid" rows={6} height={380} />
        )}
      </ChartFrame>
    </section>
  );
}

interface AttributionRow extends Record<string, unknown> {
  channel: string;
  channel_label: string;
  answer: string;
  kind: string;
  share: number;
}

function Attribution({ text }: { text: MixText }) {
  const { rows } = useMart<AttributionRow>(`select channel, channel_label, answer, kind, share from ${mart("attribution")}`);
  const answers = [...new Set((rows ?? []).map((r) => r.answer))];
  const rules = answers.filter((a) => rows?.some((r) => r.answer === a && r.kind === "rule"));
  const model = answers.find((a) => rows?.some((r) => r.answer === a && r.kind === "model"));
  const series = [
    ...rules.map((a) => ({ key: a, label: a, color: "var(--control)", pattern: PATTERN.rule, opacity: 0.55 })),
    ...(model ? [{ key: model, label: model, color: "var(--ink2)" }] : []),
  ];
  return (
    <section aria-label="Attribution">
      <Heading title="Who gets the credit: the rules, the model and the truth">
        <p>
          The rules an agency reports, the calibrated mix model, and the truth the simulator knows, on one axis. Each channel keeps its own
          color; hatching marks a rule rather than a measurement.
        </p>
      </Heading>
      <ChartFrame
        title="Share of conversions credited to each channel by the rules, the calibrated model and the truth"
        callout={text.attribution.callout}
        provenance={text.attribution.provenance}
        table={text.attribution.table}
        testId="attribution"
      >
        {rows ? (
          <GroupedBars
            groups={CHANNELS.map((c) => ({
              key: c.key,
              label: c.label,
              color: c.color,
              values: Object.fromEntries(
                series.map((s) => [s.key, rows.find((r) => r.channel === c.key && r.answer === s.key)?.share ?? null]),
              ),
              marker: rows.find((r) => r.channel === c.key && r.kind === "truth")?.share ?? null,
            }))}
            series={series}
            fmt="pct0"
            axisLabel="Share of conversions"
            barH={8}
            legend={[
              {
                label: `credit rules, top to bottom: ${rules.join(", ")}`,
                color: "var(--control)",
                kind: "bar",
                pattern: PATTERN.rule,
                opacity: 0.55,
              },
              { label: model ? `${model.toLowerCase()} (the lowest bar)` : "calibrated model", color: "var(--ink2)", kind: "bar" },
              { label: "truth (simulated)", color: "var(--ink)", kind: "diamond" },
            ]}
          />
        ) : (
          <ChartSkeleton shape="bars" rows={10} height={520} />
        )}
      </ChartFrame>
    </section>
  );
}
