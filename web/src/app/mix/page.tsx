import type { Metadata } from "next";

import { PageHeader, Pushback } from "@/components/Section";
import { Passed, Status } from "@/components/Status";
import { CHANNELS, channel } from "@/lib/channels";
import { manifest } from "@/lib/load";
import { provenanceLine } from "@/lib/manifest";

import { type Backend, MixClient, type MixText, type ReturnRow } from "./MixClient";

export const metadata: Metadata = { title: "Mix models" };

export default function Mix() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  const backends = ["own", "bayes"] as const;
  const name: Record<Backend, string> = { own: "Own", bayes: "Bayes" };
  const breakeven = m.num("policy.contribution_margin_breakeven");
  const label = (key: string) => channel(key).label.toLowerCase();

  // The channels ranked by their true half life, so the sentence names whichever is longest.
  const byHalfLife = [...CHANNELS].sort((a, b) => m.num(`sim.truth.half_life.${b.key}`) - m.num(`sim.truth.half_life.${a.key}`));
  const longest = byHalfLife[0]?.key ?? "direct_mail";
  const second = byHalfLife[1]?.key ?? "online_video";

  const per = <T,>(make: (b: Backend) => T): Record<Backend, T> => ({ own: make("own"), bayes: make("bayes") });

  const tested = channel(m.text("policy.lift_test_channel")).key;
  const floor = m.num("recovery.own.error_floor");
  const ownWorstOver = m.num("recovery.own.worst_condition_error") > floor;
  const bayesWorstOver = m.num("recovery.bayes.worst_condition_error") > floor;
  const bayesBestUnder = m.num("recovery.bayes.best_condition_error") < floor;

  const text: MixText = {
    name,
    level: v("policy.interval_level"),
    contributions: per((b) => ({
      callout: `Over ${v("sim.weeks")} weeks the ${name[b].toLowerCase()} model puts ${v(`mmm.${b}.baseline_share`)} of sales in the baseline, against ${v("sim.baseline_share")} in the simulation's truth. The channels are stacked above it in their fixed order, and ${v(`mmm.${b}.residual_share`)} of sales is left unexplained.`,
      provenance: m.prov(`mmm.${b}.baseline_share`),
    })),
    returns: per((b) => ({
      intro: `The ${name[b].toLowerCase()} model's ${v("policy.interval_level")} intervals cover the simulated truth for ${v(`mmm.${b}.covered_count`)} of ${v("policy.channel_count")} channels. A return below ${v("policy.contribution_margin_breakeven")} loses money at the ${v("policy.contribution_margin")} contribution margin.`,
      provenance: m.prov(`mmm.${b}.returns`),
    })),
    crosscheck: {
      intro:
        "Both backends fit the same data, by different methods. Where their intervals do not overlap, the answer depends on the method, and the row is marked.",
      provenance: provenanceLine({ ...m.provenance("mmm.own.returns"), model: "own and bayes" }),
    },
    curves: per((b) => {
      const displayEstimate = m.num(`mmm.${b}.marginal.${tested}`);
      const displayTruth = m.num(`sim.truth.marginal.${tested}`);
      const both = displayEstimate < breakeven && displayTruth < breakeven;
      return {
        callout: `The next dollar on email returns ${v(`mmm.${b}.marginal.email`)} under the ${name[b].toLowerCase()} model, against ${v("sim.truth.marginal.email")} in truth. The next dollar on ${label(tested)} returns ${v(`mmm.${b}.marginal.${tested}`)}, against ${v(`sim.truth.marginal.${tested}`)} in truth${both ? `, both below the break even of ${v("policy.contribution_margin_breakeven")}` : ""}.`,
        provenance: m.prov(`mmm.${b}.returns`),
      };
    }),
    halfLives: per((b) => ({
      callout: `In truth ${label(longest)} carries over longest, a half life of ${v(`sim.truth.half_life.${longest}`)} weeks; the ${name[b].toLowerCase()} model reads ${v(`mmm.${b}.half_life.${longest}`)}. The next longest, ${label(second)} at ${v(`sim.truth.half_life.${second}`)} weeks, is read as ${v(`mmm.${b}.half_life.${second}`)}.`,
      provenance: m.prov(`mmm.${b}.returns`),
    })),
    recovery: {
      callout: `Against the stated error floor of ${v("recovery.own.error_floor")}, the own backend's median absolute error is worst at ${v("recovery.own.worst_condition")}, ${v("recovery.own.worst_condition_error")}${ownWorstOver ? ", over the floor" : ""}. The Bayesian backend's is worst at ${v("recovery.bayes.worst_condition")}, ${v("recovery.bayes.worst_condition_error")}${bayesWorstOver ? ", also over it" : ""}${bayesBestUnder ? `, and under the floor at ${v("recovery.bayes.best_condition")}, ${v("recovery.bayes.best_condition_error")}` : ""}.`,
      provenance: per((b) => m.prov(`recovery.${b}.summary`)),
      tables: per((b) => {
        const t = m.table(`recovery.${b}.summary`);
        return { columns: t.columns, formats: t.formats, rows: t.rows };
      }),
      floor,
      floorLabel: `stated floor ${v("recovery.own.error_floor")}`,
      demonstration: m.text("sim.condition"),
      conditions: v("recovery.own.conditions"),
      seeds: `${v("recovery.own.seeds_per_condition")} seeds a condition for the own backend and ${v("recovery.bayes.seeds_per_condition")} for the Bayesian one`,
    },
    attribution: {
      callout: `${m.text("attribution.over_credit.every_rule") === "yes" ? "Every rule gives" : "The rules give"} ${v("attribution.over_credit.channel").toLowerCase()} far more credit than it earns: ${v("attribution.over_credit.last_touch_share")} under last touch, against a true share of ${v("attribution.over_credit.true_share")} and ${v("attribution.over_credit.model_share")} from the calibrated model. Last touch over credits it by ${v("attribution.over_credit.points")} points, ${v("attribution.over_credit.ratio")} times its true share; the worst rule, ${v("attribution.over_credit.worst_rule").toLowerCase()}, by ${v("attribution.over_credit.worst_points")} points.`,
      provenance: m.prov("attribution.comparison"),
      table: (() => {
        const t = m.table("attribution.comparison");
        return { columns: t.columns, formats: t.formats, rows: t.rows };
      })(),
    },
    initialReturns: backends.flatMap((b) =>
      m.table(`mmm.${b}.returns`).rows.map(
        (r): ReturnRow => ({
          backend: b,
          channel: channel(String(r[0])).key,
          channel_label: String(r[0]),
          roas: Number(r[1]),
          roas_lower: Number(r[2]),
          roas_upper: Number(r[3]),
          roas_true: Number(r[4]),
          covered: r[5] === "yes",
          marginal_return: Number(r[6]),
          marginal_true: Number(r[7]),
        }),
      ),
    ),
  };

  const diverged = m.num("mmm.bayes.divergences") > 0;

  return (
    <>
      <PageHeader kicker="Mix models" question="Which channels pay back, and would the models know if they were wrong?">
        <p>
          Both mix models are fitted to {v("sim.weeks")} weeks of the simulated market and graded against the returns the simulator set. The
          own backend searches carryover and saturation per channel and takes its intervals from {v("mmm.own.bootstrap_replicates")} block
          bootstrap replicates; the Bayesian backend samples a posterior. The own model&apos;s intervals hold {v("mmm.own.covered_count")}{" "}
          of the {v("policy.channel_count")} true returns, the Bayesian model&apos;s {v("mmm.bayes.covered_count")}.
        </p>
        <p className="text-base">
          {diverged ? <Status kind="critical">sampler diverged</Status> : <Passed>the sampler did not diverge</Passed>}{" "}
          <span className="text-ink2">
            {v("mmm.bayes.chains")} chains of {v("mmm.bayes.draws")} draws, {v("mmm.bayes.divergences")} divergent transitions, largest
            R-hat {v("mmm.bayes.max_rhat")}.
          </span>
        </p>
      </PageHeader>
      <MixClient text={text} />
      <Pushback>
        <p>
          The agency&apos;s attribution report gives {v("attribution.over_credit.channel").toLowerCase()}{" "}
          {v("attribution.over_credit.last_touch_share")} of conversions under last touch. The simulated truth is{" "}
          {v("attribution.over_credit.true_share")}, and the calibrated model, which absorbed a lift test that measured the channel
          directly, says {v("attribution.over_credit.model_share")}.
        </p>
        <p>
          The build puts the rules, the model and the truth on one axis and names the answer to pay for: the calibrated model&apos;s,
          because it is the only one an experiment has checked. The rules count who touched a converting customer, first, last or in
          between; none of them asks whether the customer would have bought anyway.
        </p>
      </Pushback>
    </>
  );
}
