"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import { ChartFrame, ChartSkeleton, DataTable, type TableData } from "@/components/charts/ChartFrame";
import { PATTERN } from "@/components/charts/Defs";
import { Diverging } from "@/components/charts/Diverging";
import { GroupedBars } from "@/components/charts/GroupedBars";
import { SourceChip, useApiSource } from "@/components/Controls";
import { Passed, Status } from "@/components/Status";
import { ApiError, type OptimizeBody, optimize, type Plan, savePlan, type Source } from "@/lib/api";
import { CHANNELS, channel } from "@/lib/channels";
import { mart } from "@/lib/data";
import { formatValue } from "@/lib/format";
import { useMart } from "@/lib/useMart";

// The slider walks the grid the pipeline solved the precomputed surface on: last year's weekly
// total times 1 + 0.05k for k from -8 to 8, so every position can have a row.
const GRID = Array.from({ length: 17 }, (_, k) => Math.round((1 + 0.05 * (k - 8)) * 100) / 100);
const near = (a: number, b: number) => Math.abs(a - b) < 1e-6;

export interface BudgetText {
  level: string;
  defaults: { floor: number; ceiling: number; maxChange: number };
  allocation: { callout: string; provenance: string };
  comparison: { callout: string; provenance: string; table: TableData };
  allowance: { callout: string; provenance: string };
  regret: { caption: string; provenance: string; initial: TableData };
  equalization: { statement: string; provenance: string; converged: boolean };
}

interface SurfaceRow extends Record<string, unknown> {
  surface: string;
  budget: number;
  share: number;
  channel: string;
  spend: number;
  at_bound: string;
  expected_profit: number;
  profit_lower: number;
  profit_upper: number;
  degenerate: boolean;
}
interface LastYearRow extends Record<string, unknown> {
  channel: string;
  last_year: number;
}
interface ComparisonRow extends Record<string, unknown> {
  plan: string;
  label: string;
  true_profit_weekly: number;
  gain_weekly: number;
  gain_annual: number;
}
interface AllowanceRow extends Record<string, unknown> {
  channel: string;
  allowance: number;
  implied_acquisition_cost: number;
  binds: boolean;
  at_bound: string;
}
interface RegretRow extends Record<string, unknown> {
  model: string;
  seeds: number;
  share_captured: number;
  share_captured_lower: number;
  share_captured_upper: number;
  gain_over_last_year: number;
  gain_lower: number;
  gain_upper: number;
  beats_last_year_share: number;
}

interface View {
  source: "live" | "precomputed";
  budget: number | null;
  rows: { channel: string; spend: number; lastYear: number | null; atBound: string }[];
  expectedProfit: number;
  profitLower: number;
  profitUpper: number;
  degenerate: boolean;
  degenerateReason: string | null;
  plan: Plan | null;
}

type Outcome = { view: View } | { empty: string; source: "live" | "precomputed"; solverFailed?: boolean } | { pending: true };

/** The surfaces the pipeline solved, keyed by the change limit each holds, read from their names. */
function surfaceFor(maxChange: number, names: string[], statedMaxChange: number): string | null {
  for (const name of names) {
    const limit = name === "default" ? statedMaxChange : Number(name.replace("max_change_", "")) / 100;
    if (Number.isFinite(limit) && near(limit, maxChange)) return name;
  }
  return null;
}

export function BudgetClient({ text }: { text: BudgetText }) {
  const { defaults } = text;
  const api = useApiSource();
  const [share, setShare] = useState(1);
  const [maxChange, setMaxChange] = useState(defaults.maxChange);
  const [floors, setFloors] = useState<Record<string, number>>(() => Object.fromEntries(CHANNELS.map((c) => [c.key, defaults.floor])));
  const [ceilings, setCeilings] = useState<Record<string, number>>(() =>
    Object.fromEntries(CHANNELS.map((c) => [c.key, defaults.ceiling])),
  );
  const [live, setLive] = useState<Outcome>({ pending: true });

  const surface = useMart<SurfaceRow>(
    `select surface, budget, budget_share_of_last_year as share, channel, spend, at_bound, expected_profit, profit_lower, profit_upper, degenerate from ${mart("budget_surface")}`,
  );
  const lastYear = useMart<LastYearRow>(`select channel, last_year from ${mart("budget_plan")} where plan = 'calibrated'`);

  const lastYearBy = useMemo(() => new Map((lastYear.rows ?? []).map((r) => [r.channel, r.last_year])), [lastYear.rows]);
  const lastYearTotal = (lastYear.rows ?? []).reduce((sum, r) => sum + r.last_year, 0);
  const surfaceNames = useMemo(() => [...new Set((surface.rows ?? []).map((r) => r.surface))], [surface.rows]);
  const statedBounds = CHANNELS.every((c) => near(floors[c.key] ?? NaN, defaults.floor) && near(ceilings[c.key] ?? NaN, defaults.ceiling));

  const body = useMemo((): OptimizeBody | null => {
    if (!lastYear.rows) return null;
    const uniformFloor = CHANNELS.every((c) => near(floors[c.key] ?? NaN, floors[CHANNELS[0]!.key] ?? NaN));
    const uniformCeiling = CHANNELS.every((c) => near(ceilings[c.key] ?? NaN, ceilings[CHANNELS[0]!.key] ?? NaN));
    // The API takes explicit floors and ceilings in weekly dollars; a share that is the same for
    // every channel goes as a share.
    const perChannel = (shares: Record<string, number>) =>
      Object.fromEntries(CHANNELS.map((c) => [c.key, (shares[c.key] ?? 0) * (lastYearBy.get(c.key) ?? 0)]));
    return {
      total_budget: Math.round(share * lastYearTotal * 100) / 100,
      max_change_share: maxChange,
      ...(uniformFloor ? { floor_share: floors[CHANNELS[0]!.key] } : { floors: perChannel(floors) }),
      ...(uniformCeiling ? { ceiling_share: ceilings[CHANNELS[0]!.key] } : { ceilings: perChannel(ceilings) }),
    };
  }, [share, maxChange, floors, ceilings, lastYear.rows, lastYearBy, lastYearTotal]);

  // With the API awake, every position of every control is solved on the server, 400 ms after the
  // reader stops moving it.
  useEffect(() => {
    if (api !== "live" || !body) return;
    const controller = new AbortController();
    setLive({ pending: true });
    const timer = window.setTimeout(() => {
      optimize(body, controller.signal).then(
        (answer) =>
          setLive({
            view: {
              source: "live",
              budget: body.total_budget,
              rows: CHANNELS.map((c) => {
                const a = answer.plan.allocation.find((x) => x.channel === c.key);
                return { channel: c.key, spend: a?.spend ?? 0, lastYear: a?.last_year ?? null, atBound: a?.at_bound ?? "" };
              }),
              expectedProfit: answer.plan.expected_profit,
              profitLower: answer.plan.profit_lower,
              profitUpper: answer.plan.profit_upper,
              degenerate: answer.plan.degenerate,
              degenerateReason: answer.plan.degenerate_reason,
              plan: answer.plan,
            },
          }),
        (err: unknown) => {
          if (controller.signal.aborted) return;
          const detail =
            err instanceof ApiError ? `${err.message} (status ${err.status})` : err instanceof Error ? err.message : String(err);
          // The API answers 409 when the solver ran and did not converge, 422 when the inputs are infeasible.
          const solverFailed = err instanceof ApiError && err.status === 409;
          setLive({ empty: `The optimizer found no plan for these inputs: ${detail}.`, source: "live", solverFailed });
        },
      );
    }, 400);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [api, body]);

  const precomputed = useMemo((): Outcome => {
    if (!surface.rows || !lastYear.rows) return { pending: true };
    if (!statedBounds)
      return {
        source: "precomputed",
        empty: `The precomputed surface was solved at the stated floor of ${formatValue(defaults.floor, "pct0")} and ceiling of ${formatValue(defaults.ceiling, "pct0")} of last year's spend, so it has no row for other floors or ceilings. The live API solves any of them.`,
      };
    const name = surfaceFor(maxChange, surfaceNames, defaults.maxChange);
    if (!name)
      return {
        source: "precomputed",
        empty: `The precomputed surface has no row for a change limit of ${formatValue(maxChange, "pct0")}. It was solved at ${surfaceNames
          .map((n) => formatValue(n === "default" ? defaults.maxChange : Number(n.replace("max_change_", "")) / 100, "pct0"))
          .sort((a, b) => Number.parseFloat(a) - Number.parseFloat(b))
          .join(", ")}; the live API solves any limit.`,
      };
    const rows = surface.rows.filter((r) => r.surface === name && near(r.share, share));
    if (rows.length === 0)
      return {
        source: "precomputed",
        empty: `No plan at ${formatValue(share, "pct0")} of last year's budget under a ${formatValue(maxChange, "pct0")} change limit: the optimizer found no allocation that meets every constraint there, so the surface has no row.`,
      };
    const first = rows[0]!;
    return {
      view: {
        source: "precomputed",
        budget: first.budget,
        rows: CHANNELS.map((c) => {
          const r = rows.find((x) => x.channel === c.key);
          return { channel: c.key, spend: r?.spend ?? 0, lastYear: lastYearBy.get(c.key) ?? null, atBound: r?.at_bound ?? "" };
        }),
        expectedProfit: first.expected_profit,
        profitLower: first.profit_lower,
        profitUpper: first.profit_upper,
        degenerate: first.degenerate,
        degenerateReason: null,
        plan: null,
      },
    };
  }, [surface.rows, lastYear.rows, statedBounds, maxChange, surfaceNames, share, lastYearBy, defaults]);

  const outcome: Outcome = api === "live" ? live : precomputed;
  const sourceNow: "live" | "precomputed" = api === "live" ? "live" : "precomputed";
  const view = "view" in outcome ? outcome.view : null;

  const allocationTable: TableData | null = view
    ? {
        columns: ["Channel", "Plan (weekly)", "Last year (weekly)", "Bound"],
        formats: ["text", "usd0", "usd0", "text"],
        rows: view.rows.map((r) => [channel(r.channel).label, r.spend, r.lastYear, r.atBound]),
      }
    : null;

  const reset = () => {
    setShare(1);
    setMaxChange(defaults.maxChange);
    setFloors(Object.fromEntries(CHANNELS.map((c) => [c.key, defaults.floor])));
    setCeilings(Object.fromEntries(CHANNELS.map((c) => [c.key, defaults.ceiling])));
  };

  return (
    <div className="space-y-10">
      {/* On a phone the slider sits directly above the allocation it moves; on a wide screen the
          controls, the profit and the save form share the left column. */}
      <div className="flex flex-col gap-5 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start">
        <div className="contents lg:block lg:space-y-5 lg:min-w-0">
          <div className="order-1">
            <Controls
              share={share}
              setShare={setShare}
              maxChange={maxChange}
              setMaxChange={setMaxChange}
              floors={floors}
              setFloors={setFloors}
              ceilings={ceilings}
              setCeilings={setCeilings}
              reset={reset}
              budget={view?.budget ?? null}
              source={sourceNow}
            />
          </div>
          <div className="order-3">
            <Profit outcome={outcome} level={text.level} />
          </div>
          <div className="order-4">
            <SavePlan api={api} body={body} />
          </div>
        </div>
        <div className="order-2 min-w-0">
          <ChartFrame
            title="The plan beside last year's mix, weekly spend by channel"
            callout={text.allocation.callout}
            provenance={text.allocation.provenance}
            table={allocationTable}
            testId="alloc-chart"
            controls={
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink2">
                <span>Numbers from</span>
                <SourceChip source={sourceNow} testId="budget-source" />
                {view ? <span className="num">at {formatValue(share, "pct0")} of last year&apos;s budget</span> : null}
              </div>
            }
          >
            {view ? (
              <GroupedBars
                groups={view.rows.map((r) => ({
                  key: r.channel,
                  label: channel(r.channel).label,
                  values: { plan: r.spend, last_year: r.lastYear },
                  chip: r.atBound ? <BoundChip bound={r.atBound} /> : null,
                }))}
                series={[
                  { key: "plan", label: "the plan", color: "var(--ink2)" },
                  { key: "last_year", label: "last year's mix", color: "var(--chart-bg)", pattern: PATTERN.baseline },
                ]}
                fmt="usd0"
                axisLabel="Weekly spend"
                showValues
                barH={12}
                legend={[
                  { label: "the plan, in the channel's color", color: "var(--ink2)", kind: "bar" },
                  { label: "last year's mix", color: "transparent", kind: "bar", pattern: PATTERN.baseline },
                ]}
                colorBy={(key, series) => (series === "plan" ? channel(key).color : undefined)}
              />
            ) : "empty" in outcome ? (
              <div className="min-h-[200px] flex flex-col items-start justify-center gap-3" data-testid="alloc-empty">
                {outcome.solverFailed ? <Status kind="critical">solver did not converge</Status> : null}
                <p className="prose text-sm">{outcome.empty}</p>
                <button
                  type="button"
                  onClick={reset}
                  className="text-xs px-2.5 py-1 border border-hairline rounded text-ink2 hover:text-ink"
                >
                  Back to the stated constraints
                </button>
              </div>
            ) : (
              <ChartSkeleton shape="bars" rows={14} height={520} />
            )}
          </ChartFrame>
        </div>
      </div>
      <Comparison text={text} />
      <Allowance text={text} />
      <Regret text={text} />
    </div>
  );
}

function BoundChip({ bound }: { bound: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full border border-hairline bg-surface px-1.5 py-px text-[11px] text-ink2 leading-4"
      data-bound={bound}
    >
      {bound}
    </span>
  );
}

function Controls({
  share,
  setShare,
  maxChange,
  setMaxChange,
  floors,
  setFloors,
  ceilings,
  setCeilings,
  reset,
  budget,
  source,
}: {
  share: number;
  setShare: (v: number) => void;
  maxChange: number;
  setMaxChange: (v: number) => void;
  floors: Record<string, number>;
  setFloors: (v: Record<string, number>) => void;
  ceilings: Record<string, number>;
  setCeilings: (v: Record<string, number>) => void;
  reset: () => void;
  budget: number | null;
  source: "live" | "precomputed";
}) {
  const first = GRID[0] ?? share;
  const last = GRID[GRID.length - 1] ?? share;
  const pct = (v: number) => Math.round(v * 100);
  const stepPct = pct((GRID[1] ?? first) - first);
  return (
    <div className="card p-4 sm:p-5 space-y-4" data-testid="budget-controls">
      <div>
        <div className="flex items-baseline justify-between gap-3">
          <label htmlFor="budget-share" className="text-sm font-semibold">
            Total weekly budget
          </label>
          <SourceChip source={source} />
        </div>
        <p className="mt-1 text-sm">
          <span className="font-display text-2xl num" data-testid="budget-share">
            {formatValue(share, "pct0")}
          </span>{" "}
          <span className="text-ink2">of last year&apos;s weekly total</span>
          {budget !== null ? (
            <span className="text-ink2">
              , <span className="num text-ink">{formatValue(budget, "usd0")}</span> a week
            </span>
          ) : null}
        </p>
        <input
          id="budget-share"
          type="range"
          min={pct(first)}
          max={pct(last)}
          step={stepPct}
          value={pct(share)}
          onChange={(e) => {
            // Snap to the grid the surface was solved on, whatever rounding the browser applied.
            const wanted = Number(e.target.value) / 100;
            const snapped = GRID.reduce((best, g) => (Math.abs(g - wanted) < Math.abs(best - wanted) ? g : best), first);
            setShare(snapped);
          }}
          aria-valuetext={`${formatValue(share, "pct0")} of last year's weekly budget`}
          data-testid="budget-slider"
          className="mt-2"
        />
        <div className="flex justify-between text-xs text-ink2 num">
          <span>{formatValue(first, "pct0")}</span>
          <span>{formatValue(GRID[Math.floor(GRID.length / 2)] ?? share, "pct0")}</span>
          <span>{formatValue(last, "pct0")}</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <label htmlFor="max-change" className="text-sm">
          Largest change for any channel, share of last year
        </label>
        <span className="inline-flex items-center gap-1">
          <input
            id="max-change"
            type="number"
            min={5}
            max={100}
            step={5}
            value={pct(maxChange)}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (Number.isFinite(n) && n > 0) setMaxChange(n / 100);
            }}
            className="w-20 text-right"
            data-testid="max-change"
          />
          <span className="text-sm text-ink2">%</span>
        </span>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-ink2 hover:text-ink">Floors and ceilings by channel, as a share of last year</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Channel</th>
                <th scope="col" className="num">
                  Floor, %
                </th>
                <th scope="col" className="num">
                  Ceiling, %
                </th>
              </tr>
            </thead>
            <tbody>
              {CHANNELS.map((c) => (
                <tr key={c.key}>
                  <td>{c.label}</td>
                  <td className="num">
                    <input
                      type="number"
                      aria-label={`Floor for ${c.label}, percent of last year`}
                      min={0}
                      max={100}
                      step={5}
                      value={pct(floors[c.key] ?? 0)}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        if (Number.isFinite(n) && n >= 0) setFloors({ ...floors, [c.key]: n / 100 });
                      }}
                      className="w-20 text-right"
                    />
                  </td>
                  <td className="num">
                    <input
                      type="number"
                      aria-label={`Ceiling for ${c.label}, percent of last year`}
                      min={100}
                      step={5}
                      value={pct(ceilings[c.key] ?? 0)}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        if (Number.isFinite(n) && n >= 100) setCeilings({ ...ceilings, [c.key]: n / 100 });
                      }}
                      className="w-20 text-right"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <button type="button" onClick={reset} className="text-xs px-2.5 py-1 border border-hairline rounded text-ink2 hover:text-ink">
        Reset to last year&apos;s budget and the stated constraints
      </button>
    </div>
  );
}

function Profit({ outcome, level }: { outcome: Outcome; level: string }) {
  const view = "view" in outcome ? outcome.view : null;
  let status: ReactNode = null;
  if (view) {
    status = view.degenerate ? (
      <Status kind="warning">degenerate operating point{view.degenerateReason ? `: ${view.degenerateReason}` : ""}</Status>
    ) : (
      <Passed>not a degenerate operating point</Passed>
    );
  }
  const solver = view?.plan?.solver_status ?? null;
  return (
    <div className="card p-4 sm:p-5" data-testid="profit-card" aria-live="polite">
      <p className="text-sm font-semibold">Expected incremental profit</p>
      {view ? (
        <>
          <p className="mt-1">
            <span className="font-display text-[2rem] num" data-testid="expected-profit">
              {formatValue(view.expectedProfit, "usd0")}
            </span>{" "}
            <span className="text-ink2 text-sm">a week</span>
          </p>
          <p className="text-sm text-ink2 num" data-testid="expected-profit-interval">
            {view.plan ? formatValue(view.plan.level, "pct0") : level} interval {formatValue(view.profitLower, "usd0")} to{" "}
            {formatValue(view.profitUpper, "usd0")}
          </p>
          <p className="text-sm mt-2">{status}</p>
          {view.plan ? (
            <p className="text-xs text-ink2 mt-2">
              Marginal returns equalized across {formatValue(view.plan.interior_channels, "int")} interior channels:{" "}
              {view.plan.marginal_equalized ? "yes" : "no"}, spread {formatValue(view.plan.marginal_spread, "float3")}. Solver: {solver}.
              Inputs hash <span className="mono">{view.plan.inputs_hash}</span>.
            </p>
          ) : null}
        </>
      ) : "empty" in outcome ? (
        <p className="text-sm text-ink2 mt-1" data-testid="expected-profit">
          No plan, so no profit to show.
        </p>
      ) : (
        <div className="skeleton h-9 w-40 mt-2" aria-busy="true" />
      )}
    </div>
  );
}

interface Saved {
  source: Source;
  reason?: string;
  planId: string;
  hash: string;
  createdAt: string;
}

function SavePlan({ api, body }: { api: Source | "probing"; body: OptimizeBody | null }) {
  // The write token lives in this component's memory only: never stored, never put in a URL.
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const save = async () => {
    if (!body) return;
    setBusy(true);
    setProblem(null);
    try {
      const answer = await savePlan({ ...body, note: "saved from the budget page" }, token);
      setSaved({
        source: answer.source,
        reason: answer.reason,
        planId: answer.body.plan_id,
        hash: answer.body.plan.inputs_hash,
        createdAt: answer.body.created_at,
      });
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const chipSource = api === "live" ? "live" : api === "probing" ? "probing" : "recorded";
  return (
    <div className="card p-4 sm:p-5 space-y-3" data-testid="save-plan">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">Save this plan to the registry</p>
        <SourceChip source={chipSource} testId="save-source" />
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-ink2 flex flex-col gap-1">
          Write token
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="w-44"
            data-testid="write-token"
          />
        </label>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || !body}
          className="px-3 py-1.5 rounded bg-ink text-surface text-sm font-semibold disabled:opacity-50"
          data-testid="save-plan-button"
        >
          {busy ? "Saving" : "Save this plan"}
        </button>
      </div>
      <p className="text-xs text-ink2">
        Writes need the token and a live API. Without either, the button shows the save made when the session was recorded, labeled as such.
      </p>
      {saved ? (
        <div className="border-t border-hairline pt-3 text-sm space-y-1" data-testid="saved-plan">
          <SourceChip
            source={saved.source}
            text={saved.source === "live" ? "live API: saved" : `recorded session (${saved.reason ?? "API asleep"})`}
          />
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 mt-2">
            <dt className="text-ink2">Plan id</dt>
            <dd className="mono text-xs break-all" data-testid="saved-plan-id">
              {saved.planId}
            </dd>
            <dt className="text-ink2">Inputs hash</dt>
            <dd className="mono text-xs" data-testid="saved-plan-hash">
              {saved.hash}
            </dd>
            <dt className="text-ink2">Saved at</dt>
            <dd className="mono text-xs">{saved.createdAt}</dd>
          </dl>
          {saved.source === "recorded" ? (
            <p className="text-xs text-ink2">
              This is the plan the recording saved at last year&apos;s budget, not necessarily the plan on screen.
            </p>
          ) : null}
        </div>
      ) : null}
      {problem ? <p className="text-sm text-ink2">The save failed: {problem}</p> : null}
    </div>
  );
}

function Comparison({ text }: { text: BudgetText }) {
  const { rows } = useMart<ComparisonRow>(
    `select plan, label, true_profit_weekly, gain_weekly, gain_annual from ${mart("budget_comparison")}`,
  );
  return (
    <section aria-label="The plans compared">
      <h2 className="text-[1.6rem] leading-tight mb-4">The plan against the alternatives, judged on the true curves</h2>
      <ChartFrame
        title="Gain in weekly profit over last year's mix, at last year's budget"
        callout={text.comparison.callout}
        provenance={text.comparison.provenance}
        table={text.comparison.table}
        testId="comparison"
      >
        {rows ? (
          <Diverging
            items={rows
              .filter((r) => r.plan !== "last_year")
              .map((r) => ({
                key: r.plan,
                label: r.label,
                value: r.gain_weekly,
                note: `true profit ${formatValue(r.true_profit_weekly, "usd0")} a week`,
              }))}
            fmt="usd0"
            axisLabel="Change in weekly profit against last year's mix"
            positiveLabel="more profit than last year's mix"
            negativeLabel="less profit"
          />
        ) : (
          <ChartSkeleton shape="bars" rows={4} height={180} />
        )}
      </ChartFrame>
    </section>
  );
}

function Allowance({ text }: { text: BudgetText }) {
  const { rows } = useMart<AllowanceRow>(`select channel, allowance, implied_acquisition_cost, binds, at_bound from ${mart("allowance")}`);
  const table: TableData | null = rows
    ? {
        columns: ["Channel", "Allowance per customer", "Implied acquisition cost", "Binds", "Bound"],
        formats: ["text", "usd2", "usd2", "text", "text"],
        rows: CHANNELS.map((c) => {
          const r = rows.find((x) => x.channel === c.key);
          return [
            c.label,
            r?.allowance ?? null,
            r?.implied_acquisition_cost ?? null,
            r ? (r.binds ? "yes" : "no") : null,
            r?.at_bound ?? null,
          ];
        }),
      }
    : null;
  return (
    <section aria-label="The acquisition cost allowance">
      <h2 className="text-[1.6rem] leading-tight mb-4">What a customer may cost, by channel</h2>
      <ChartFrame
        title="Allowance per customer beside what the plan pays to acquire one"
        callout={text.allowance.callout}
        provenance={text.allowance.provenance}
        table={table}
        testId="allowance"
      >
        {rows ? (
          <GroupedBars
            groups={CHANNELS.map((c) => {
              const r = rows.find((x) => x.channel === c.key);
              return {
                key: c.key,
                label: c.label,
                values: { allowance: r?.allowance ?? null, implied: r?.implied_acquisition_cost ?? null },
                chip: r?.binds ? (
                  <BoundChip bound={r.at_bound === "allowance (infeasible)" ? "allowance cannot be met" : "allowance binds"} />
                ) : null,
              };
            })}
            series={[
              { key: "allowance", label: "allowance per customer", color: "var(--chart-bg)", pattern: PATTERN.baseline },
              { key: "implied", label: "implied acquisition cost of the plan", color: "var(--ink2)" },
            ]}
            colorBy={(key, series) => (series === "implied" ? channel(key).color : undefined)}
            fmt="usd0"
            axisLabel="Dollars per acquired customer"
            showValues
            barH={12}
            legend={[
              { label: "allowance per customer", color: "transparent", kind: "bar", pattern: PATTERN.baseline },
              { label: "implied acquisition cost of the plan, in the channel's color", color: "var(--ink2)", kind: "bar" },
            ]}
          />
        ) : (
          <ChartSkeleton shape="bars" rows={14} height={420} />
        )}
      </ChartFrame>
    </section>
  );
}

function Regret({ text }: { text: BudgetText }) {
  const { rows } = useMart<RegretRow>(
    `select model, seeds, share_captured, share_captured_lower, share_captured_upper, gain_over_last_year, gain_lower, gain_upper, beats_last_year_share from ${mart("budget_regret")}`,
  );
  const table: TableData = rows
    ? {
        columns: text.regret.initial.columns,
        formats: text.regret.initial.formats,
        rows: rows.map((r) => [
          r.model,
          r.seeds,
          r.share_captured,
          r.share_captured_lower,
          r.share_captured_upper,
          r.gain_over_last_year,
          r.gain_lower,
          r.gain_upper,
          r.beats_last_year_share,
        ]),
      }
    : text.regret.initial;
  return (
    <section aria-label="The regret study" className="space-y-5">
      <div className="card p-4 sm:p-5">
        <h2 className="text-[1.35rem] leading-tight mb-2">The regret study</h2>
        <p className="prose text-sm text-ink2 mb-3">{text.regret.caption}</p>
        <DataTable table={table} dense={false} caption="Regret across simulated markets" />
        <p className="text-xs text-ink2 mt-3">{text.regret.provenance}</p>
      </div>
      <div className="card p-4 sm:p-5" data-testid="equalization">
        <h2 className="text-[1.35rem] leading-tight mb-2">Is the plan at the margin?</h2>
        <p className="text-sm mb-2">
          {text.equalization.converged ? (
            <Passed>every optimizer start converged</Passed>
          ) : (
            <Status kind="critical">solver did not converge</Status>
          )}
        </p>
        <p className="prose text-sm leading-relaxed">{text.equalization.statement}</p>
        <p className="text-xs text-ink2 mt-3">{text.equalization.provenance}</p>
      </div>
    </section>
  );
}
