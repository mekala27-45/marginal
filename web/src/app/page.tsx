import type { Metadata } from "next";
import Link from "next/link";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { Forest } from "@/components/charts/Forest";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { Passed, Status } from "@/components/Status";
import { channel } from "@/lib/channels";
import { manifest } from "@/lib/load";

import { type Backend, type BackendText, OverviewModels, type ReturnRow } from "./OverviewModels";

export const metadata: Metadata = { title: "Overview" };

export default function Overview() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  const seeds = v("budget.regret.calibrated.seeds");
  const calibrated = m.num("budget.regret.calibrated.share_captured");
  const uncalibrated = m.num("budget.regret.uncalibrated.share_captured");
  // The plain sentence beside the headline depends on the regret study itself, not on a hope.
  const close = Math.abs(calibrated - uncalibrated) < 0.01;

  const text: Record<Backend, BackendText> = {
    own: {
      name: "Own",
      kpiCallout: `Over all ${v("sim.weeks")} weeks the own model puts ${v("mmm.own.baseline_share")} of sales in the baseline, against ${v("sim.baseline_share")} in the simulation's truth, and leaves ${v("mmm.own.residual_share")} of sales unexplained.`,
      kpiProvenance: m.prov("mmm.own.baseline_share"),
      returnsCallout: `The own model's ${v("policy.interval_level")} intervals cover the simulated truth for ${v("mmm.own.covered_count")} of ${v("policy.channel_count")} channels. They are narrow, and narrow and wrong is the failure the recovery study measures.`,
      returnsProvenance: m.prov("mmm.own.returns"),
    },
    bayes: {
      name: "Bayes",
      kpiCallout: `Over all ${v("sim.weeks")} weeks the Bayesian model puts ${v("mmm.bayes.baseline_share")} of sales in the baseline, against ${v("sim.baseline_share")} in the simulation's truth, and leaves ${v("mmm.bayes.residual_share")} of sales unexplained.`,
      kpiProvenance: m.prov("mmm.bayes.baseline_share"),
      returnsCallout: `The Bayesian model's ${v("policy.interval_level")} intervals cover the simulated truth for ${v("mmm.bayes.covered_count")} of ${v("policy.channel_count")} channels, at the price of intervals wide enough to hold most of the plausible answers.`,
      returnsProvenance: m.prov("mmm.bayes.returns"),
    },
  };

  // The first paint draws the return chart from the manifest's copy of the table; the page then
  // swaps in the same rows queried from returns.parquet.
  const initialReturns: ReturnRow[] = (["own", "bayes"] as const).flatMap((backend) =>
    m.table(`mmm.${backend}.returns`).rows.map((r) => ({
      backend,
      channel: channel(String(r[0])).key,
      channel_label: String(r[0]),
      roas: Number(r[1]),
      roas_lower: Number(r[2]),
      roas_upper: Number(r[3]),
      roas_true: Number(r[4]),
      covered: r[5] === "yes",
    })),
  );

  const geo = m.table("geo.estimates");
  const didCovers = m.text("geo.did.covers_truth") === "yes";
  const scCovers = m.text("geo.sc.covers_truth") === "yes";

  return (
    <>
      <PageHeader kicker={`Quarterly review, as of ${m.asOf}`} question="What does the next dollar of marketing buy, and how sure are we?">
        <p>
          Moving last year&apos;s budget between channels, without adding a dollar, is worth{" "}
          {v("budget.headline.gain_over_last_year_annual")} a year on the simulated market. The mix model that recommends the move was
          graded against a market whose true returns are known, then corrected by a pre-registered geo lift test on {v("geo.channel")}.
        </p>
        <p className="text-ink2 text-base">
          Every figure here is read from the published manifest or queried from its marts in your browser.
        </p>
      </PageHeader>

      <section aria-labelledby="headline" className="mb-4">
        <h2 id="headline" className="sr-only">
          The budget numbers
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="card p-5 sm:p-6" data-testid="headline-gain">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">Gain from reallocating the same budget</p>
            <p className="font-display text-[2.8rem] sm:text-[3.4rem] leading-none mt-3 num font-medium" data-testid="headline-gain-value">
              {v("budget.headline.gain_over_last_year_annual")}
            </p>
            <p className="mt-3 text-sm leading-relaxed">
              a year over last year&apos;s mix on the demonstration market, or {v("budget.headline.gain_over_last_year_weekly")} a week.
              Across the {seeds} seed regret study the calibrated plan&apos;s weekly gain ran from{" "}
              {v("budget.regret.calibrated.gain_lower")} to {v("budget.regret.calibrated.gain_upper")}.
            </p>
          </div>
          <div className="card p-5 sm:p-6" data-testid="headline-share">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">Share of the best possible gain</p>
            <p className="font-display text-[2.8rem] sm:text-[3.4rem] leading-none mt-3 num font-medium" data-testid="headline-share-value">
              {v("budget.headline.share_captured")}
            </p>
            <p className="mt-3 text-sm leading-relaxed">
              of the gain the truth optimal plan would have made, captured by the calibrated model&apos;s plan. Across {seeds} seeds it
              captured {v("budget.regret.calibrated.share_captured")}, from {v("budget.regret.calibrated.share_captured_lower")} to{" "}
              {v("budget.regret.calibrated.share_captured_upper")}.
            </p>
          </div>
        </div>
        <p className="prose mt-4 text-[0.98rem] leading-relaxed" data-testid="headline-plain">
          Said plainly: on the {seeds} seed regret study the calibrated and uncalibrated models capture{" "}
          {close ? "shares within a point of each other" : "different shares"}, {v("budget.regret.calibrated.share_captured")} against{" "}
          {v("budget.regret.uncalibrated.share_captured")}. The lift test did not buy a better budget on average. It bought a better
          estimate of the channel it tested, which is what the{" "}
          <Link href="/experiments/" className="underline">
            experiments page
          </Link>{" "}
          shows.
        </p>
      </section>

      <Section
        id="models"
        title="The quarter and the return on each channel"
        intro={
          <p>
            Both mix models are shown against the simulated truth. The own backend is a fixed search with a bootstrap; the Bayesian backend
            samples a posterior. Switch between them to see how each one splits the same sales.
          </p>
        }
      >
        <OverviewModels
          text={text}
          initialReturns={initialReturns}
          breakeven={{
            value: m.num("policy.contribution_margin_breakeven"),
            label: `break even at a ${v("policy.contribution_margin")} margin`,
          }}
          level={v("policy.interval_level")}
        />
      </Section>

      <Section
        id="experiment"
        title={`The latest experiment: a geo lift test on ${v("geo.channel")}`}
        intro={
          <p>
            Spend on {v("geo.channel")} {m.num("geo.spend_change") === -1 ? "was switched off" : `changed by ${v("geo.spend_change")}`} in{" "}
            {v("geo.treated_geos")} of {v("sim.geos")} geos for {v("geo.window_weeks")} weeks, weeks {v("geo.start_week")} to{" "}
            {v("geo.end_week")}. The plan was registered before the data was read: plan hash{" "}
            <span className="mono">{v("geo.plan_hash")}</span>, registered {v("geo.registered_at")}.
          </p>
        }
      >
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-5 items-start">
          <ChartFrame
            title="Incremental revenue over the test window, each estimator against the truth"
            callout={`The difference in differences estimate is ${v("geo.did.estimate")}, an error of ${v("geo.did.error")} against the truth of ${v("geo.truth")}, and its interval misses it. The synthetic control estimate is ${v("geo.sc.estimate")}, an error of ${v("geo.sc.error")}, and its interval covers it.`}
            provenance={m.prov("geo.estimates")}
            table={{ columns: geo.columns, formats: geo.formats, rows: geo.rows }}
            testId="geo-estimates"
          >
            <Forest
              rows={geo.rows.map((r, i) => ({
                key: `method-${i}`,
                label: String(r[0]),
                color: i === 0 ? "var(--ink)" : "var(--control)",
                estimate: Number(r[1]),
                low: Number(r[2]),
                high: Number(r[3]),
                truth: Number(r[4]),
                note: r[5] === "yes" ? "the interval covers the truth" : "the interval excludes the truth",
              }))}
              fmt="usd0"
              axisLabel="Incremental revenue over the window"
              intervalLabel={`with its ${v("policy.interval_level")} interval`}
            />
          </ChartFrame>
          <div className="card p-5 text-sm leading-relaxed space-y-3" data-testid="latest-experiment">
            <p className="text-xs uppercase tracking-[0.12em] text-ink2">Result against the truth</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-ink2">Difference in differences</dt>
              <dd className="num text-right">{v("geo.did.estimate")}</dd>
              <dt className="text-ink2">Interval</dt>
              <dd className="num text-right">
                {v("geo.did.lower")} to {v("geo.did.upper")}
              </dd>
              <dt className="text-ink2">Truth (simulated)</dt>
              <dd className="num text-right">{v("geo.truth")}</dd>
              <dt className="text-ink2">Plan hash</dt>
              <dd className="mono text-right" data-testid="overview-plan-hash">
                {v("geo.plan_hash")}
              </dd>
            </dl>
            <p>
              {didCovers ? <Passed>interval covers the truth</Passed> : <Status kind="serious">interval excludes the truth</Status>}{" "}
              <span className="text-ink2">for difference in differences;</span>{" "}
              {scCovers ? <Passed>interval covers the truth</Passed> : <Status kind="serious">interval excludes the truth</Status>}{" "}
              <span className="text-ink2">for the synthetic control.</span>
            </p>
            <p className="text-ink2">
              The sample ratio gate {v("geo.srm_passed")} at p = {v("geo.srm_p")}.{" "}
              <Link className="underline text-ink" href="/experiments/">
                The full test
              </Link>
            </p>
          </div>
        </div>
      </Section>

      <Pushback>
        <p>
          The market is simulated, so a CMO will ask what these return figures mean for a real brand. The honest answer is nothing, until
          the same pipeline runs on the brand&apos;s own weekly panel.
        </p>
        <p>
          What the build proves is narrower and checkable. The mix models recover returns they were never shown to within a stated error: a
          median absolute error of {v("recovery.own.demonstration.median_abs_error")} for the own backend and{" "}
          {v("recovery.bayes.demonstration.median_abs_error")} for the Bayesian one on the demonstration condition. And a pre-registered
          experiment corrects them: the lift test cut the own model&apos;s error on the tested channel from{" "}
          {v("calibrate.own.recovery.tested_error_before")} to {v("calibrate.own.recovery.tested_error_after")} across{" "}
          {v("calibrate.own.recovery.seeds")} seeds.
        </p>
      </Pushback>
    </>
  );
}
