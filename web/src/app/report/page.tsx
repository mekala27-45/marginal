import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DataTable, type TableData } from "@/components/charts/ChartFrame";
import { ReadyWithoutQueries } from "@/components/Controls";
import { CHANNELS, channel } from "@/lib/channels";
import { bundle, manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { PrintButton } from "./PrintButton";

export const metadata: Metadata = { title: "The quarterly review" };

function table(m: ManifestView, key: string): TableData {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

function Exhibit({ m, id, title, children }: { m: ManifestView; id: string; title: string; children?: ReactNode }) {
  return (
    <figure className="my-6" data-exhibit={id}>
      <figcaption className="font-sans text-sm font-semibold mb-2">{title}</figcaption>
      {children ?? <DataTable table={table(m, id)} dense={false} max={60} label={title} />}
      <p className="font-sans text-xs text-ink2 mt-2">{m.prov(id)}</p>
    </figure>
  );
}

const list = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

export default function Report() {
  const m = manifest();
  const b = bundle();
  const v = (key: string) => m.v(key);
  const tested = channel(m.text("geo.channel")).label.toLowerCase();
  const infeasible = m.text("budget.allowance_infeasible");
  const binds = CHANNELS.filter((c) => m.text(`budget.bound.${c.key}`) === "allowance").map((c) => c.label.toLowerCase());
  const close = Math.abs(m.num("budget.regret.calibrated.share_captured") - m.num("budget.regret.uncalibrated.share_captured")) < 0.01;
  const didCovers = m.text("geo.did.covers_truth") === "yes";
  const scCovers = m.text("geo.sc.covers_truth") === "yes";
  const excludeAfter = m.text("calibrate.own.covers_after") === "no" && m.text("calibrate.bayes.covers_after") === "no";
  const sure = m.num("targeting.hillstrom.sure_things.policy_value_test");
  const learnersLost =
    m.num("targeting.hillstrom.t_learner.policy_value_test") < sure && m.num("targeting.hillstrom.x_learner.policy_value_test") < sure;
  const criteoClear = ["t_learner", "x_learner", "sure_things"].every((p) => m.num(`targeting.criteo.${p}.qini_lower`) > 0);
  const overPredicts = m.num("clv.holdout.purchases_predicted_over_actual") > 0;

  return (
    <>
      <ReadyWithoutQueries />
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6 no-print">
        <p className="text-xs uppercase tracking-[0.14em] text-ink2">The quarterly review, as a memo</p>
        <PrintButton />
      </div>
      <article className="report-sheet card px-5 py-8 sm:px-12 sm:py-12 max-w-[1040px]" data-testid="memo">
        <div className="memo">
          <p className="font-sans text-xs uppercase tracking-[0.14em] text-ink2">
            Marketing science, for the chief marketing officer · as of {m.asOf}
          </p>
          <h1 className="text-[2.2rem] sm:text-[2.6rem] leading-[1.08] mt-2 mb-4">
            The quarterly review: what the next dollar buys at {b.brand}
          </h1>
          <p>
            Every figure in this memo is a value or a table in the manifest the pipeline published; none is typed by hand. The market is
            simulated with known truth, so the memo can say not only what the models estimate but how far each estimate sits from the
            answer.
          </p>

          <section>
            <h2>The budget numbers</h2>
            <p>
              Holding the budget at last year&apos;s {v("budget.total_weekly")} a week and moving it between channels is worth{" "}
              <strong>{v("budget.headline.gain_over_last_year_annual")} a year</strong>, {v("budget.headline.gain_over_last_year_weekly")} a
              week, on the simulated market. The plan captures <strong>{v("budget.headline.share_captured")}</strong> of the gain the truth
              optimal plan would make, which is {v("budget.headline.gain_optimal_annual")} a year.
            </p>
            <p>
              Both numbers come from the demonstration market. Across {v("budget.regret.calibrated.seeds")} markets with known truth, the
              calibrated model&apos;s plan captured {v("budget.regret.calibrated.share_captured")} of the optimal gain, from{" "}
              {v("budget.regret.calibrated.share_captured_lower")} to {v("budget.regret.calibrated.share_captured_upper")}, and beat last
              year&apos;s mix in {v("budget.regret.calibrated.beats_last_year")} of them. The uncalibrated model captured{" "}
              {v("budget.regret.uncalibrated.share_captured")}
              {close ? ", within a point" : ""}. Calibration did not buy a better budget on average; it bought a better estimate of the
              channel it tested.
            </p>
            <Exhibit m={m} id="budget.allocation" title="The plan at last year's budget, weekly" />
            <Exhibit m={m} id="budget.regret" title="The regret study across simulated markets" />
          </section>

          <section>
            <h2>What the lift test said, and how it moved the model</h2>
            <p>
              A geo lift test switched {tested} off in {v("geo.treated_geos")} of {v("sim.geos")} geos for {v("geo.window_weeks")} weeks,
              registered before its data was read under plan hash <span className="mono text-[0.9em]">{v("geo.plan_hash")}</span>.
              Difference in differences put the incremental revenue at {v("geo.did.estimate")}, from {v("geo.did.lower")} to{" "}
              {v("geo.did.upper")}; the synthetic control at {v("geo.sc.estimate")}. The truth, known only because the market is simulated,
              is {v("geo.truth")}.{" "}
              {didCovers ? "The difference in differences interval covers it" : "The difference in differences interval misses it"};{" "}
              {scCovers ? "the synthetic control's covers it" : "the synthetic control's misses it too"}.
            </p>
            <p>
              Taken into the models as a measurement, the test moved the own model&apos;s return on {tested} from{" "}
              {v("calibrate.own.roas_before")} to {v("calibrate.own.roas_after")} and the Bayesian model&apos;s from{" "}
              {v("calibrate.bayes.roas_before")} to {v("calibrate.bayes.roas_after")}, against a true {v("calibrate.own.roas_true")}.
              {excludeAfter ? " Both intervals now sit just off the truth: the models believe the test more than they should." : ""} Across{" "}
              {v("calibrate.own.recovery.seeds")} simulated markets, the own model&apos;s error on the tested channel fell from{" "}
              {v("calibrate.own.recovery.tested_error_before")} to {v("calibrate.own.recovery.tested_error_after")}.
            </p>
            <Exhibit m={m} id="geo.estimates" title="The lift test, each estimator against the truth" />
            <Exhibit m={m} id="calibrate.own.before_after" title="The own model on the tested channel, before and after" />
          </section>

          <section>
            <h2>The targeting result</h2>
            <p>
              On the Hillstrom test split, the only real randomized experiment in the build,{" "}
              {learnersLost ? "neither uplift learner beat" : "the uplift learners beat"} the sure things rule:{" "}
              {v("targeting.hillstrom.t_learner.policy_value_test")} and {v("targeting.hillstrom.x_learner.policy_value_test")} per thousand
              customers on the list against {v("targeting.hillstrom.sure_things.policy_value_test")}, with Qini intervals that include zero.
              On simulated customers, where each response is known, the X learner reached{" "}
              {v("targeting.sim.quadrant.x_learner.persuadable")} of the persuadables and made{" "}
              {v("targeting.sim.x_learner.policy_value_test")} per thousand against {v("targeting.sim.everyone.policy_value_test")} for
              contacting everyone.
              {criteoClear ? " On the full Criteo release every targeting policy beat random." : ""}
            </p>
            <Exhibit m={m} id="targeting.hillstrom.policies" title="The policies on the Hillstrom test split" />
          </section>

          <section>
            <h2>Lifetime value and the acquisition allowance</h2>
            <p>
              A BG/NBD and Gamma-Gamma model fitted to {v("clv.customers")} Online Retail II customers through {v("clv.calibration_end")}{" "}
              predicted {v("clv.holdout.predicted_purchases_total")} purchases in the holdout year against{" "}
              {v("clv.holdout.actual_purchases_total")} actual, {v("clv.holdout.purchases_predicted_over_actual")}
              {overPredicts ? ", an over-prediction the allowance inherits" : ""}. The mean lifetime value is {v("clv.clv.mean")}, the
              median {v("clv.clv.median")}.
            </p>
            <p>
              At the {v("policy.contribution_margin")} margin and a payback share of {v("policy.clv_payback_share")}, that is an allowance
              of {v("clv.allowance.overall")} per acquired customer, from {v("clv.allowance.one_time")} for one time buyers to{" "}
              {v("clv.allowance.frequent")} for frequent ones. In the plan it binds on {list(binds)}, and {infeasible.toLowerCase()} cannot
              meet it at any spend the constraints allow, so it is held at its floor.
            </p>
            <Exhibit m={m} id="clv.segments" title="Lifetime value and allowance by purchase frequency" />
            <Exhibit m={m} id="clv.allowance_by_channel" title="The allowance by channel" />
          </section>

          <section>
            <h2>Attribution beside the truth</h2>
            <p>
              {m.text("attribution.over_credit.every_rule") === "yes" ? "Every" : "Each"} credit rule gives{" "}
              {v("attribution.over_credit.channel").toLowerCase()} around {v("attribution.over_credit.last_touch_share")} of conversions.
              Its incremental share is {v("attribution.over_credit.true_share")}, and the calibrated model says{" "}
              {v("attribution.over_credit.model_share")}. The rules agree with each other and not with the truth: last touch ranks the
              channels with an agreement of {v("attribution.grade.last_touch.rank_agreement")} and misses each share by{" "}
              {v("attribution.grade.last_touch.mean_abs_error_points")} points on average.
            </p>
            <Exhibit
              m={m}
              id="attribution.comparison"
              title="Share of conversions by channel: the rules, the truth and the calibrated model"
            />
            <Exhibit m={m} id="attribution.grades" title="Each rule graded against the truth" />
          </section>

          <section>
            <h2>Limitations</h2>
            <ul>
              <li>
                The market is simulated. The return figures describe the simulator, not a real brand, until the pipeline runs on a real
                weekly panel.
              </li>
              <li>
                The own model&apos;s intervals are too narrow: they hold the truth for {v("mmm.own.covered_count")} of{" "}
                {v("policy.channel_count")} channels here, and {v("recovery.own.coverage_overall")} of the time across the recovery study,
                against a stated {v("policy.interval_level")}.
              </li>
              <li>
                The recovery study&apos;s median error is over the stated floor of {v("recovery.own.error_floor")} for the own backend at
                its worst condition ({v("recovery.own.worst_condition")}, {v("recovery.own.worst_condition_error")}) and for the Bayesian
                backend at its worst ({v("recovery.bayes.worst_condition")}, {v("recovery.bayes.worst_condition_error")}).
              </li>
              <li>
                The allowance comes from a UK online gift retailer&apos;s customers, {v("data.retail.first_date")} to{" "}
                {v("data.retail.last_date")}, not from {b.brand}&apos;s.
              </li>
              <li>
                The regret study ran on {v("budget.regret.calibrated.seeds")} markets and the Bayesian recovery study on{" "}
                {v("recovery.bayes.seeds_per_condition")} seeds per condition; both intervals would narrow with more.
              </li>
              <li>Criteo publishes no value per visit, so its policy values are counted in visits, not dollars.</li>
            </ul>
          </section>

          <section>
            <h2>What the CMO would push back on</h2>
            <p>
              <em>These returns are from a simulation.</em> They are, and they mean nothing for a real brand until the same pipeline runs on
              its own panel. What the build proves is that the method recovers known returns within a stated error and that a pre-registered
              experiment corrects it.
            </p>
            <p>
              <em>The plan cuts the channel we like.</em> {channel(m.text("geo.channel")).label} goes to its change limit,{" "}
              {v(`budget.change.${channel(m.text("geo.channel")).key}`)}. The answer is the lift test that measured it directly and an
              allowance a real brand would set from its own customers.
            </p>
            <p>
              <em>The uplift model lost to a rule.</em> On the real test the intervals include zero, the simulator shows the learners
              winning when there is signal, and the policy value curve is what tells the cases apart.
            </p>
          </section>
        </div>
      </article>
    </>
  );
}
