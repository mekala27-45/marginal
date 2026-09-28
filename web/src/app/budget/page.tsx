import type { Metadata } from "next";

import { PageHeader, Pushback } from "@/components/Section";
import { CHANNELS, channel } from "@/lib/channels";
import { manifest } from "@/lib/load";

import { BudgetClient, type BudgetText } from "./BudgetClient";

export const metadata: Metadata = { title: "Budget" };

const list = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

export default function Budget() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  const label = (key: string) => channel(key).label.toLowerCase();
  const bound = (key: string) => m.text(`budget.bound.${key}`);
  const change = (key: string) => m.num(`budget.change.${key}`);

  const raised = CHANNELS.filter((c) => change(c.key) > 0).map((c) => c.key);
  const cut = CHANNELS.filter((c) => change(c.key) < 0).map((c) => c.key);
  const interior = CHANNELS.filter((c) => bound(c.key) === "interior").map((c) => c.key);
  const atLimit = CHANNELS.filter((c) => bound(c.key) === "change limit").map((c) => c.key);
  const allowanceBinds = CHANNELS.filter((c) => bound(c.key) === "allowance").map((c) => c.key);
  const infeasible = m.text("budget.allowance_infeasible");
  const regret = m.table("budget.regret");

  const text: BudgetText = {
    level: v("budget.level"),
    defaults: {
      floor: m.num("policy.budget_floor_share"),
      ceiling: m.num("policy.budget_ceiling_share"),
      maxChange: m.num("policy.budget_max_change_share"),
    },
    allocation: {
      callout: `At last year's budget the calibrated plan moves ${list(interior.map((k) => `${label(k)} by ${v(`budget.change.${k}`)}`))}, the channels it leaves free to move. ${list(
        atLimit.map((k) => label(k)),
      ).replace(/^./, (c) => c.toUpperCase())} sit at the change limit of ${v("budget.max_change_share")}.`,
      provenance: m.prov("budget.allocation"),
    },
    comparison: {
      callout: `At last year's budget, judged on the true curves, the calibrated plan earns ${v("budget.calibrated.true_profit_weekly")} a week, against ${v("budget.headline.last_year_profit_weekly")} for last year's mix and ${v("budget.truth.true_profit_weekly")} for the plan chosen with the truth in hand. The uncalibrated model's plan earns ${v("budget.uncalibrated.true_profit_weekly")}; an equal split changes profit by ${v("budget.headline.equal_split_gain_annual")} a year.`,
      provenance: m.prov("budget.comparison"),
      table: (() => {
        const t = m.table("budget.comparison");
        return { columns: t.columns, formats: t.formats, rows: t.rows };
      })(),
    },
    allowance: {
      callout: `${infeasible} is held at its floor, the lowest spend the change limit allows, because its curve never meets its allowance of ${v(`clv.allowance.channel.${channel(infeasible).key}`)}: at every spend the plan could choose, a customer acquired through it costs more than that.${allowanceBinds.length ? ` The allowance also binds on ${list(allowanceBinds.map((k) => label(k)))}.` : ""} Each allowance is the mean lifetime value of the customers a channel brings, times the ${v("policy.contribution_margin")} margin, times a payback share of ${v("policy.clv_payback_share")}.`,
      provenance: `Allowance: ${m.prov("clv.allowance_by_channel")} Implied acquisition cost: ${m.prov("budget.allocation")}`,
    },
    regret: {
      caption: `The same optimizer, run on ${v("budget.regret.calibrated.seeds")} simulated markets whose truth is known: the share of the truth optimal gain each model's plan captured, and its weekly gain over last year's mix, with intervals across seeds.`,
      provenance: m.prov("budget.regret"),
      initial: { columns: regret.columns, formats: regret.formats, rows: regret.rows },
    },
    equalization: {
      statement: `At last year's budget, marginal returns ${m.text("budget.marginal_equalized") === "yes" ? "are equalized" : "are not equalized"} across the ${v("budget.interior_channels")} interior channels, with a largest spread of ${v("budget.marginal_spread")}. The operating point is ${v("budget.interior")}: ${v("budget.interior_reason")}. ${v("budget.starts_converged")} of ${v("budget.starts")} optimizer starts converged (${v("budget.solver_status").toLowerCase()}).`,
      provenance: m.prov("budget.marginal_equalized"),
      converged: m.num("budget.starts_converged") === m.num("budget.starts"),
    },
  };

  return (
    <>
      <PageHeader kicker="Budget" question="Where should the money go, with the total held fixed?">
        <p>
          At last year&apos;s total of {v("budget.total_weekly")} a week, the calibrated model&apos;s plan adds to{" "}
          {list(raised.map((k) => label(k)))} and takes from {list(cut.map((k) => label(k)))}. Judged on the true curves, it earns{" "}
          {v("budget.headline.gain_over_last_year_weekly")} a week more than last year&apos;s mix.
        </p>
        <p className="text-base text-ink2">
          Move the budget and the constraints. With the live API awake, every position is solved on the server; asleep, the page reads the
          surface the pipeline solved in advance, and says which one you are looking at.
        </p>
      </PageHeader>
      <BudgetClient text={text} />
      <Pushback>
        <p>
          The model says cut the channel the CFO likes: {label("display_retargeting")} goes to its change limit,{" "}
          {v("budget.change.display_retargeting")}, and {label(channel(infeasible).key)} to its floor,{" "}
          {v(`budget.change.${channel(infeasible).key}`)}.
        </p>
        <p>
          The build&apos;s answer is not the model&apos;s say so. It is the lift test that measured display directly,{" "}
          {v("geo.did.estimate")} of incremental revenue over {v("geo.window_weeks")} weeks where the uncorrected model had implied{" "}
          {v("calibrate.own.implied_before")}, and an acquisition allowance that a real brand would set from its own customers&apos;
          lifetime value. The one used here, {v("clv.allowance.overall")} per customer, comes from a UK online gift retailer&apos;s purchase
          history, not from Alderquist&apos;s.
        </p>
      </Pushback>
    </>
  );
}
