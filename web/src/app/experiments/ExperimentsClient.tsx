"use client";

import { useEffect, useState } from "react";

import { ChartFrame, ChartSkeleton, type TableData } from "@/components/charts/ChartFrame";
import { PATTERN } from "@/components/charts/Defs";
import { Forest } from "@/components/charts/Forest";
import { GroupedBars } from "@/components/charts/GroupedBars";
import { Histogram } from "@/components/charts/Histogram";
import { LineChart } from "@/components/charts/LineChart";
import { Segmented, SourceChip, useApiSource } from "@/components/Controls";
import { Passed, Status } from "@/components/Status";
import { type Answer, type ExperimentResponse, read } from "@/lib/api";
import { channel } from "@/lib/channels";
import { mart } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { useMart } from "@/lib/useMart";

type Panel = { callout: string; provenance: string };

export interface ExperimentsText {
  level: string;
  experimentId: string;
  series: Panel;
  placebo: Panel;
  power: Panel & { table: TableData; designWeeks: number; designRemoved: number };
  calibration: Panel & { table: TableData };
  lift: Panel & { table: TableData };
  recovery: Panel;
  email: Panel;
  segments: Record<string, string>;
  segmentProvenance: string;
  srmProvenance: string;
}

interface SeriesRow extends Record<string, unknown> {
  week: number;
  treated: number;
  synthetic: number;
  in_window: boolean;
}
interface ResultRow extends Record<string, unknown> {
  experiment_id: string;
  plan_hash: string;
  registered_at: string;
  registered_via: string;
  channel: string;
  start_week: number;
  end_week: number;
  did_estimate: number;
  did_lower: number;
  did_upper: number;
  sc_estimate: number;
  sc_lower: number;
  sc_upper: number;
  sc_p_value: number;
  placebo_permutations: number;
  truth: number;
  srm_p_value: number;
  srm_passed: boolean;
  power_at_true_effect: number;
}
interface PowerRow extends Record<string, unknown> {
  spend_multiplier: number;
  window_weeks: number;
  power: number;
}

export function GeoTest({ text }: { text: ExperimentsText }) {
  const series = useMart<SeriesRow>(`select week, treated, synthetic, in_window from ${mart("geo_series")} order by week`);
  const placebo = useMart<{ placebo_effect: number }>(`select placebo_effect from ${mart("geo_placebo")}`);
  const result = useMart<ResultRow>(`select * from ${mart("geo_result")}`);
  const power = useMart<PowerRow>(
    `select spend_multiplier, window_weeks, power from ${mart("geo_power")} order by window_weeks, spend_multiplier`,
  );
  const r = result.rows?.[0];
  const window = (series.rows ?? []).filter((s) => s.in_window);
  const windows = [...new Set((power.rows ?? []).map((p) => p.window_weeks))];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ChartFrame
          title="Weekly sales in the treated geos against their synthetic control"
          callout={text.series.callout}
          provenance={text.series.provenance}
          table={
            series.rows
              ? {
                  columns: ["Week", "Treated geos", "Synthetic control", "In the test window"],
                  formats: ["int", "usd0", "usd0", "text"],
                  rows: series.rows.map((s) => [s.week, s.treated, s.synthetic, s.in_window ? "yes" : "no"]),
                }
              : null
          }
          testId="geo-series"
        >
          {series.rows ? (
            <LineChart
              series={[
                {
                  key: "treated",
                  name: "treated geos",
                  color: "var(--ink)",
                  points: series.rows.map((s) => ({ x: s.week, y: s.treated })),
                },
                {
                  key: "synthetic",
                  name: "synthetic control",
                  color: "var(--control)",
                  dash: "7 3",
                  points: series.rows.map((s) => ({ x: s.week, y: s.synthetic })),
                },
              ]}
              shades={window.length ? [{ from: window[0]!.week, to: window[window.length - 1]!.week, label: "test window" }] : []}
              xFmt="int"
              yFmt="usd0"
              xLabel="Week"
              yLabel="Weekly sales, treated geos"
              height={300}
              zero={false}
            />
          ) : (
            <ChartSkeleton shape="lines" height={300} />
          )}
        </ChartFrame>
        <ChartFrame
          title="The estimated effect against what chance produces"
          callout={text.placebo.callout}
          provenance={text.placebo.provenance}
          table={
            placebo.rows
              ? {
                  columns: ["Placebo effect"],
                  formats: ["usd0"],
                  rows: [...placebo.rows].sort((a, b) => a.placebo_effect - b.placebo_effect).map((p) => [p.placebo_effect]),
                }
              : null
          }
          testId="placebo-chart"
        >
          {placebo.rows && r ? (
            <Histogram
              values={placebo.rows.map((p) => p.placebo_effect)}
              fmt="usd0"
              xLabel="Incremental revenue over the window"
              yLabel="placebo assignments"
              distributionLabel={`placebo effects, ${formatValue(r.placebo_permutations, "int")} assignments`}
              rules={[
                { x: r.did_estimate, label: "difference in differences", color: "var(--ink)" },
                { x: r.sc_estimate, label: "synthetic control", color: "var(--ink)", dash: "5 3" },
              ]}
              truth={{ x: r.truth, label: "truth (simulated)" }}
              height={300}
            />
          ) : (
            <ChartSkeleton shape="lines" height={300} />
          )}
        </ChartFrame>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-5 items-start">
        <ChartFrame
          title="Power to detect the true effect, by spend removed and test length"
          callout={text.power.callout}
          provenance={text.power.provenance}
          table={text.power.table}
          testId="power"
        >
          {power.rows ? (
            <LineChart
              series={windows.map((w, i) => ({
                key: `w${w}`,
                name: `${formatValue(w, "int")} weeks`,
                color: i === windows.length - 1 ? "var(--seq-4)" : "var(--seq-2)",
                dash: i === windows.length - 1 ? undefined : "7 3",
                points: (power.rows ?? [])
                  .filter((p) => p.window_weeks === w)
                  .map((p) => ({ x: 1 - p.spend_multiplier, y: p.power }))
                  .sort((a, b) => a.x - b.x),
              }))}
              marks={[
                { x: text.power.designRemoved, y: r?.power_at_true_effect ?? 1, label: "the registered design", color: "var(--ink)" },
              ]}
              xFmt="pct0"
              yFmt="pct0"
              xLabel="Share of spend removed in the treated geos"
              yLabel="Power"
              yDomain={[0, 1]}
              height={260}
              extraLegend={[{ label: "the registered design", color: "var(--ink)", kind: "dot" }]}
            />
          ) : (
            <ChartSkeleton shape="lines" height={260} />
          )}
        </ChartFrame>
        <Registration result={r ?? null} experimentId={text.experimentId} />
      </div>
    </div>
  );
}

function Registration({ result, experimentId }: { result: ResultRow | null; experimentId: string }) {
  const api = useApiSource();
  const [record, setRecord] = useState<Answer<ExperimentResponse> | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    read<ExperimentResponse>(`/v1/experiments/${experimentId}`, "experiment").then(
      (a) => {
        if (live) setRecord(a);
      },
      (err: unknown) => {
        if (live) setProblem(err instanceof Error ? err.message : String(err));
      },
    );
    return () => {
      live = false;
    };
  }, [experimentId]);
  const posted = record?.body.results[0];
  return (
    <div className="card p-4 sm:p-5 text-sm space-y-4" data-testid="registration">
      <div>
        <p className="text-xs uppercase tracking-[0.12em] text-ink2 mb-2">Registered before the data was read</p>
        {result ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-ink2">Plan hash</dt>
            <dd className="mono text-right" data-testid="plan-hash">
              {result.plan_hash}
            </dd>
            <dt className="text-ink2">Registered</dt>
            <dd className="mono text-right text-xs">{result.registered_at}</dd>
            <dt className="text-ink2">Through</dt>
            <dd className="text-right">{result.registered_via === "local" ? "the local registry" : result.registered_via}</dd>
            <dt className="text-ink2">Weeks</dt>
            <dd className="num text-right">
              {formatValue(result.start_week, "int")} to {formatValue(result.end_week, "int")}
            </dd>
            <dt className="text-ink2">Sample ratio</dt>
            <dd className="text-right">
              {result.srm_passed ? (
                <Passed>passed, p = {formatValue(result.srm_p_value, "float3")}</Passed>
              ) : (
                <Status kind="critical">SRM failed</Status>
              )}
            </dd>
          </dl>
        ) : (
          <div className="skeleton h-24" aria-busy="true" />
        )}
      </div>
      <div className="border-t border-hairline pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <p className="text-xs uppercase tracking-[0.12em] text-ink2">The registry&apos;s record</p>
          <SourceChip source={record ? record.source : api === "probing" ? "probing" : api} testId="registry-source" />
        </div>
        {record ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-ink2">Experiment</dt>
            <dd className="mono text-right text-xs break-all">{record.body.experiment_id}</dd>
            <dt className="text-ink2">Plan hash</dt>
            <dd className="mono text-right">{record.body.plan_hash}</dd>
            <dt className="text-ink2">Registered</dt>
            <dd className="mono text-right text-xs">{record.body.registered_at}</dd>
            {posted ? (
              <>
                <dt className="text-ink2">Result posted</dt>
                <dd className="num text-right">
                  {formatValue(posted.incremental_revenue, "usd0")} ({posted.method})
                </dd>
              </>
            ) : null}
          </dl>
        ) : problem ? (
          <p className="text-ink2">The registry record did not load: {problem}</p>
        ) : (
          <div className="skeleton h-20" aria-busy="true" />
        )}
        {record?.source === "recorded" ? (
          <p className="text-xs text-ink2 mt-2">
            From the session recorded against the API, which registers the same plan hash on its own clock.
          </p>
        ) : null}
      </div>
    </div>
  );
}

interface CalibrationRow extends Record<string, unknown> {
  backend: string;
  channel: string;
  channel_label: string;
  roas_before: number;
  roas_before_lower: number;
  roas_before_upper: number;
  roas_after: number;
  roas_after_lower: number;
  roas_after_upper: number;
  roas_true: number;
  implied_lift_before: number;
  implied_lift_after: number;
  experiment_lift: number;
  truth_lift: number;
  covers_before: boolean;
  covers_after: boolean;
  recovery_seeds: number;
  recovery_error_before: number;
  recovery_error_after: number;
  tested_error_before: number;
  tested_error_after: number;
}

const BACKEND_NAME: Record<string, string> = { own: "Own", bayes: "Bayes" };

export function Calibration({ text }: { text: ExperimentsText }) {
  const { rows } = useMart<CalibrationRow>(`select * from ${mart("calibration")} order by backend desc`);
  const color = rows?.[0] ? channel(rows[0].channel).color : "var(--ink)";
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ChartFrame
          title="The tested channel's return, before and after the lift test"
          callout={text.calibration.callout}
          provenance={text.calibration.provenance}
          table={text.calibration.table}
          testId="calibration-return"
        >
          {rows ? (
            <>
              <Forest
                rows={rows.flatMap((c) => [
                  {
                    key: `${c.backend}-before`,
                    label: `${BACKEND_NAME[c.backend] ?? c.backend}, before`,
                    color: "var(--control)",
                    estimate: c.roas_before,
                    low: c.roas_before_lower,
                    high: c.roas_before_upper,
                    truth: c.roas_true,
                    note: c.covers_before ? "the interval covers the truth" : "the interval excludes the truth",
                  },
                  {
                    key: `${c.backend}-after`,
                    label: `${BACKEND_NAME[c.backend] ?? c.backend}, after`,
                    color,
                    estimate: c.roas_after,
                    low: c.roas_after_lower,
                    high: c.roas_after_upper,
                    truth: c.roas_true,
                    note: c.covers_after ? "the interval covers the truth" : "the interval excludes the truth",
                  },
                ])}
                fmt="float2"
                axisLabel="Return on ad spend, the tested channel"
                intervalLabel={`with its ${text.level} interval; gray before, the channel's color after`}
              />
              <ul className="mt-3 text-xs space-y-1">
                {rows.map((c) => (
                  <li key={c.backend}>
                    <span className="text-ink2">{BACKEND_NAME[c.backend] ?? c.backend} after calibration: </span>
                    {c.covers_after ? (
                      <Passed>interval covers the truth</Passed>
                    ) : (
                      <Status kind="serious">interval excludes the truth</Status>
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <ChartSkeleton shape="forest" rows={4} height={200} />
          )}
        </ChartFrame>
        <ChartFrame
          title="The lift each model implied for the test window, against the experiment and the truth"
          callout={text.lift.callout}
          provenance={text.lift.provenance}
          table={text.lift.table}
          testId="calibration-lift"
        >
          {rows ? (
            <Forest
              rows={rows.flatMap((c) => [
                {
                  key: `${c.backend}-before`,
                  label: `${BACKEND_NAME[c.backend] ?? c.backend}, before`,
                  color: "var(--control)",
                  estimate: c.implied_lift_before,
                  truth: c.truth_lift,
                },
                {
                  key: `${c.backend}-after`,
                  label: `${BACKEND_NAME[c.backend] ?? c.backend}, after`,
                  color,
                  estimate: c.implied_lift_after,
                  truth: c.truth_lift,
                },
              ])}
              fmt="usd0"
              axisLabel="Incremental revenue over the test window"
              estimateLabel="lift the model implied"
              reference={rows[0] ? { value: rows[0].experiment_lift, label: "the experiment's estimate" } : undefined}
            />
          ) : (
            <ChartSkeleton shape="forest" rows={4} height={200} />
          )}
        </ChartFrame>
      </div>
      <ChartFrame
        title="Median error across simulated markets, before and after calibrating on one lift test"
        callout={text.recovery.callout}
        provenance={text.recovery.provenance}
        table={
          rows
            ? {
                columns: [
                  "Model",
                  "Seeds",
                  "All channels, before",
                  "All channels, after",
                  "Tested channel, before",
                  "Tested channel, after",
                ],
                formats: ["text", "int", "pct1", "pct1", "pct1", "pct1"],
                rows: rows.map((c) => [
                  BACKEND_NAME[c.backend] ?? c.backend,
                  c.recovery_seeds,
                  c.recovery_error_before,
                  c.recovery_error_after,
                  c.tested_error_before,
                  c.tested_error_after,
                ]),
              }
            : null
        }
        testId="calibration-recovery"
      >
        {rows ? (
          <GroupedBars
            groups={rows.flatMap((c) => [
              {
                key: `${c.backend}-tested`,
                label: `${BACKEND_NAME[c.backend] ?? c.backend} model, the tested channel`,
                values: { before: c.tested_error_before, after: c.tested_error_after },
              },
              {
                key: `${c.backend}-all`,
                label: `${BACKEND_NAME[c.backend] ?? c.backend} model, all channels`,
                values: { before: c.recovery_error_before, after: c.recovery_error_after },
              },
            ])}
            series={[
              { key: "before", label: "before the lift test", color: "var(--chart-bg)", pattern: PATTERN.baseline },
              { key: "after", label: "after", color },
            ]}
            fmt="pct0"
            axisLabel="Median absolute error of the return, across seeds"
            showValues
            barH={12}
            legend={[
              { label: "before the lift test", color: "transparent", kind: "bar", pattern: PATTERN.baseline },
              { label: "after", color, kind: "bar" },
            ]}
          />
        ) : (
          <ChartSkeleton shape="bars" rows={8} height={260} />
        )}
      </ChartFrame>
    </div>
  );
}

interface SrmRow extends Record<string, unknown> {
  arm: string;
  observed: number;
  expected: number;
  p_value: number;
  passed: boolean;
  alpha: number;
}
interface EffectRow extends Record<string, unknown> {
  arm: string;
  outcome: string;
  effect: number;
  lower: number;
  upper: number;
  treated_mean: number;
  control_mean: number;
}
interface SegmentRow extends Record<string, unknown> {
  arm: string;
  outcome: string;
  segment: string;
  effect: number;
  lower: number;
  upper: number;
  p_value: number;
  p_adjusted: number;
  significant: boolean;
  n: number;
}

const ARM_NAME: Record<string, string> = { mens: "Men's email", womens: "Women's email", control: "No email" };
const OUTCOMES: { value: string; label: string; fmt: string }[] = [
  { value: "visit", label: "Visit", fmt: "pct2" },
  { value: "conversion", label: "Conversion", fmt: "pct2" },
  { value: "spend", label: "Spend", fmt: "usd2" },
];

export function Hillstrom({ text }: { text: ExperimentsText }) {
  const srm = useMart<SrmRow>(`select arm, observed, expected, p_value, passed, alpha from ${mart("email_srm")}`);
  const effects = useMart<EffectRow>(`select arm, outcome, effect, lower, upper, treated_mean, control_mean from ${mart("email_effects")}`);
  const segments = useMart<SegmentRow>(`select * from ${mart("email_segments")}`);
  const [arm, setArm] = useState("mens");
  const [outcome, setOutcome] = useState("conversion");
  const fmtOf = (o: string) => OUTCOMES.find((x) => x.value === o)?.fmt ?? "float4";
  const shown = (segments.rows ?? []).filter((s) => s.arm === arm && s.outcome === outcome);
  const alpha = srm.rows?.[0]?.alpha ?? null;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-[2fr_3fr] gap-5 items-start">
        <div className="card p-4 sm:p-5" data-testid="srm">
          <h3 className="font-sans text-[0.95rem] font-semibold mb-2">The sample ratio gate, three arms</h3>
          {srm.rows ? (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Arm</th>
                    <th scope="col" className="num">
                      Customers
                    </th>
                    <th scope="col" className="num">
                      Expected
                    </th>
                    <th scope="col" className="num">
                      p
                    </th>
                    <th scope="col">Gate</th>
                  </tr>
                </thead>
                <tbody>
                  {srm.rows.map((s) => (
                    <tr key={s.arm}>
                      <td>{ARM_NAME[s.arm] ?? s.arm}</td>
                      <td className="num">{formatValue(s.observed, "int")}</td>
                      <td className="num">{formatValue(s.expected, "int")}</td>
                      <td className="num">{formatValue(s.p_value, "float3")}</td>
                      <td className="whitespace-nowrap">
                        {s.passed ? <Passed>passed</Passed> : <Status kind="critical">SRM failed</Status>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ChartSkeleton shape="table" rows={3} height={120} />
          )}
          <p className="text-xs text-ink2 mt-3">
            The gate is a chi square test of the counts against an equal split
            {alpha !== null ? `, failing below ${formatValue(alpha, "float3")}` : ""}. No effect is shown while it fails.{" "}
            {text.srmProvenance}
          </p>
        </div>
        <ChartFrame
          title="Effect of each email against no email, by outcome"
          callout={text.email.callout}
          provenance={text.email.provenance}
          table={
            effects.rows
              ? {
                  columns: ["Arm", "Outcome", "No email", "Email", "Effect", "Lower", "Upper"],
                  formats: ["text", "text", "float4", "float4", "float4", "float4", "float4"],
                  rows: effects.rows.map((e) => [
                    ARM_NAME[e.arm] ?? e.arm,
                    e.outcome,
                    e.control_mean,
                    e.treated_mean,
                    e.effect,
                    e.lower,
                    e.upper,
                  ]),
                }
              : null
          }
          testId="email-effects"
        >
          {effects.rows ? (
            <div className="space-y-4">
              {OUTCOMES.map((o) => (
                <div key={o.value}>
                  <p className="text-[12.5px] font-semibold mb-1">{o.label}</p>
                  <Forest
                    rows={(effects.rows ?? [])
                      .filter((e) => e.outcome === o.value)
                      .map((e) => ({
                        key: e.arm,
                        label: ARM_NAME[e.arm] ?? e.arm,
                        color: e.arm === "mens" ? "var(--ink)" : "var(--control)",
                        estimate: e.effect,
                        low: e.lower,
                        high: e.upper,
                      }))}
                    fmt={o.fmt}
                    axisLabel={o.value === "spend" ? "Change in spend per customer" : `Change in the ${o.label.toLowerCase()} rate`}
                    reference={{ value: 0, label: "no effect" }}
                    intervalLabel={`with its ${text.level} interval`}
                    estimateLabel="effect"
                  />
                </div>
              ))}
            </div>
          ) : (
            <ChartSkeleton shape="forest" rows={6} height={300} />
          )}
        </ChartFrame>
      </div>
      <div className="card p-4 sm:p-5" data-testid="segments">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h3 className="font-sans text-[0.95rem] font-semibold">Effects by purchase history segment, Benjamini-Hochberg adjusted</h3>
          <div className="flex flex-wrap gap-3">
            <Segmented
              label="Arm"
              options={[
                { value: "mens", label: "Men's" },
                { value: "womens", label: "Women's" },
              ]}
              value={arm}
              onChange={setArm}
            />
            <Segmented
              label="Outcome"
              options={OUTCOMES.map(({ value, label }) => ({ value, label }))}
              value={outcome}
              onChange={setOutcome}
            />
          </div>
        </div>
        {text.segments[`${arm}.${outcome}`] ? <p className="prose text-sm mb-3">{text.segments[`${arm}.${outcome}`]}</p> : null}
        {segments.rows ? (
          <div className="overflow-x-auto" role="region" aria-label="Segment effects" tabIndex={0}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Purchase history in the prior year</th>
                  <th scope="col" className="num">
                    Customers
                  </th>
                  <th scope="col" className="num">
                    Effect
                  </th>
                  <th scope="col" className="num">
                    {text.level} interval
                  </th>
                  <th scope="col" className="num">
                    p
                  </th>
                  <th scope="col" className="num">
                    p adjusted
                  </th>
                  <th scope="col">After adjustment</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.segment} data-significant={s.significant ? "yes" : "no"} className={s.significant ? "" : "text-ink2"}>
                    <td>{s.segment}</td>
                    <td className="num">{formatValue(s.n, "int")}</td>
                    <td className="num">{formatValue(s.effect, fmtOf(outcome))}</td>
                    <td className="num">
                      {formatValue(s.lower, fmtOf(outcome))} to {formatValue(s.upper, fmtOf(outcome))}
                    </td>
                    <td className="num">{formatValue(s.p_value, "float3")}</td>
                    <td className="num">{formatValue(s.p_adjusted, "float3")}</td>
                    <td className="whitespace-nowrap">{s.significant ? <Passed>significant</Passed> : <span>not significant</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ChartSkeleton shape="table" rows={7} height={240} />
        )}
        <p className="text-xs text-ink2 mt-3">{text.segmentProvenance}</p>
      </div>
    </div>
  );
}
