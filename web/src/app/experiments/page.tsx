import type { Metadata } from "next";

import type { TableData } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback, Section } from "@/components/Section";
import { channel } from "@/lib/channels";
import { formatValue, type Scalar } from "@/lib/format";
import { manifest } from "@/lib/load";

import { Calibration, type ExperimentsText, GeoTest, Hillstrom } from "./ExperimentsClient";

export const metadata: Metadata = { title: "Experiments" };

const cell = (value: Scalar | undefined, fmt: string) => formatValue(value ?? null, fmt);

export default function Experiments() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  const name = channel(m.text("geo.channel")).label.toLowerCase();
  // The year of the email experiment, as its citation in the manifest gives it.
  const year = /\((\d{4})\)/.exec(m.text("data.hillstrom.citation"))?.[1] ?? null;

  // The power sentence names the weakest design the study tried, read from the table itself.
  const power = m.table("geo.power");
  const weakest = [...power.rows].sort((a, b) => Number(a[0]) - Number(b[0]) || Number(a[1]) - Number(b[1]))[0];
  const weakText = weakest
    ? ` A test that removed ${cell(weakest[0], "pct0")} of the spend for ${cell(weakest[1], "int")} weeks would find it ${cell(weakest[3], "pct0")} of the time.`
    : "";

  const closer = (b: string) =>
    Math.abs(m.num(`calibrate.${b}.roas_after`) - m.num(`calibrate.${b}.roas_true`)) <
    Math.abs(m.num(`calibrate.${b}.roas_before`) - m.num(`calibrate.${b}.roas_true`));
  const excludeAfter = m.text("calibrate.own.covers_after") === "no" && m.text("calibrate.bayes.covers_after") === "no";
  const cut = m.num("calibrate.own.recovery.tested_error_after") < m.num("calibrate.own.recovery.tested_error_before");
  const sameSign = m.num("geo.did.error") > 0 && m.num("geo.sc.error") > 0;
  const noPlaceboAsLarge = m.num("geo.sc.p_value") === 0;
  const sureThings = m.num("targeting.hillstrom.sure_things.policy_value_test");
  const learnersLost =
    m.num("targeting.hillstrom.t_learner.policy_value_test") < sureThings &&
    m.num("targeting.hillstrom.x_learner.policy_value_test") < sureThings;

  const ownBA = m.table("calibrate.own.before_after");
  const bayesBA = m.table("calibrate.bayes.before_after");
  const calibrationTable: TableData = {
    columns: ["", "Own, before", "Own, after", "Bayes, before", "Bayes, after", "Truth (simulated)"],
    formats: ["text", "float2", "float2", "float2", "float2", "float2"],
    rows: ownBA.rows.map((r, i) => [
      r[0] ?? null,
      r[1] ?? null,
      r[2] ?? null,
      bayesBA.rows[i]?.[1] ?? null,
      bayesBA.rows[i]?.[2] ?? null,
      r[3] ?? null,
    ]),
  };
  const ownLift = m.table("calibrate.own.lift");
  const bayesLift = m.table("calibrate.bayes.lift");
  const liftTable: TableData = {
    columns: ["", "Own", "Bayes"],
    formats: ["text", "usd0", "usd0"],
    rows: ownLift.rows.map((r, i) => [r[0] ?? null, r[1] ?? null, bayesLift.rows[i]?.[1] ?? null]),
  };

  const text: ExperimentsText = {
    level: v("policy.interval_level"),
    experimentId: m.text("geo.experiment_id"),
    series: {
      callout: `Before the test the synthetic control tracks the treated geos to within ${v("geo.sc.pre_period_rmse")} a week, the root mean square error over the ${v("geo.pre_period_weeks")} week pre-period. In the test window the treated geos run below it, and that gap is the effect of the change in ${name} spend.`,
      provenance: m.prov("geo.sc.pre_period_rmse"),
    },
    placebo: {
      callout: `Across ${v("geo.sc.placebo_permutations")} placebo assignments of the treatment to control geos, ${noPlaceboAsLarge ? `none is as large as the estimates, a placebo p value of ${v("geo.sc.p_value")}` : `the synthetic control's placebo p value is ${v("geo.sc.p_value")}`}. ${sameSign ? "Both estimates sit above" : "The estimates straddle"} the truth of ${v("geo.truth")}: the difference in differences by ${v("geo.did.error")}, the synthetic control by ${v("geo.sc.error")}.`,
      provenance: m.prov("geo.sc.p_value"),
    },
    power: {
      callout: `At the registered design, ${name} spend ${m.num("geo.spend_change") === -1 ? "switched off" : `changed by ${v("geo.spend_change")}`} in ${v("geo.treated_geos")} geos for ${v("geo.window_weeks")} weeks, the test finds the true effect with power ${v("geo.power_at_true_effect")} across ${v("geo.power_simulations")} simulated tests.${weakText}`,
      provenance: m.prov("geo.power"),
      table: { columns: power.columns, formats: power.formats, rows: power.rows },
      designWeeks: m.num("geo.window_weeks"),
      designRemoved: -m.num("geo.spend_change"),
    },
    calibration: {
      callout: `Before the lift test the own model put ${name}'s return at ${v("calibrate.own.roas_before")} and the Bayesian model at ${v("calibrate.bayes.roas_before")}, against a true ${v("calibrate.own.roas_true")}. After it, ${v("calibrate.own.roas_after")} and ${v("calibrate.bayes.roas_after")}${closer("own") && closer("bayes") ? ": both moved toward the truth" : ""}${excludeAfter ? ", and both intervals now exclude it, the price of a model that believes one test more than it should" : ""}.`,
      provenance: m.prov("calibrate.own.before_after"),
      table: calibrationTable,
    },
    lift: {
      callout: `Over the test window the own model implied ${v("calibrate.own.implied_before")} of lift before calibration and ${v("calibrate.own.implied_after")} after; the Bayesian model ${v("calibrate.bayes.implied_before")} and ${v("calibrate.bayes.implied_after")}. The experiment found ${v("calibrate.experiment_lift")}, and the truth is ${v("calibrate.truth_lift")}.`,
      provenance: m.prov("calibrate.own.lift"),
      table: liftTable,
    },
    recovery: {
      callout: `Across ${v("calibrate.own.recovery.seeds")} simulated markets, calibrating on a lift test ${cut ? "cut" : "changed"} the own model's median error on the tested channel from ${v("calibrate.own.recovery.tested_error_before")} to ${v("calibrate.own.recovery.tested_error_after")}, and across all channels from ${v("calibrate.own.recovery.error_before")} to ${v("calibrate.own.recovery.error_after")}. Over ${v("calibrate.bayes.recovery.seeds")} markets the Bayesian model went from ${v("calibrate.bayes.recovery.tested_error_before")} to ${v("calibrate.bayes.recovery.tested_error_after")} on the tested channel.`,
      provenance: m.prov("calibrate.own.recovery"),
    },
    email: {
      callout: `The men's email raised the conversion rate from ${v("email.mens.conversion.control")} to ${v("email.mens.conversion.treated")} and spend per customer by ${v("email.mens.spend.effect")}; the women's email raised conversion to ${v("email.womens.conversion.treated")} and spend by ${v("email.womens.spend.effect")}. At ${v("email.cost_per_email")} an email and a ${v("email.margin_on_spend")} margin on spend, the men's email makes ${v("email.mens.profit_per_email")} a send and the women's ${v("email.womens.profit_per_email")}.`,
      provenance: m.prov("email.effects"),
    },
    segments: {
      "mens.conversion": `${v("email.segments.mens.conversion.significant")} of ${v("email.segments.mens.conversion.count")} purchase history segments show a significant effect of the men's email on conversion after adjustment (${v("email.segments.correction")}).`,
    },
    segmentProvenance: m.prov("email.segments.mens.conversion"),
    srmProvenance: m.prov("email.srm_p"),
  };

  return (
    <>
      <PageHeader kicker="Experiments" question="What did the experiments measure, and what did they change?">
        <p>
          A geo lift test on {name}, registered before its data was read, found {v("geo.did.estimate")} of incremental revenue over{" "}
          {v("geo.window_weeks")} weeks. Fed back into both mix models as a measurement, it moved their estimate of the channel toward the
          truth. The email experiment is the one real randomized result here: Kevin Hillstrom&apos;s {v("data.hillstrom.rows")} customers,
          each sent the men&apos;s email, the women&apos;s email or nothing.
        </p>
      </PageHeader>

      <Section id="geo" title={`The geo lift test on ${name}`}>
        <GeoTest text={text} />
      </Section>

      <Section
        id="calibration"
        title="What the lift test did to the models"
        intro={
          <p>
            Each backend takes the test&apos;s estimate as a measurement of the channel&apos;s lift over the window, with the test&apos;s
            own standard error of {v("calibrate.experiment_se")}, and refits.
          </p>
        }
      >
        <Calibration text={text} />
        <div className="card p-4 sm:p-5 mt-5 max-w-3xl" data-testid="weight-test">
          <h3 className="font-sans text-[0.95rem] font-semibold mb-2">Is the weight on the experiment a choice or a corner?</h3>
          <p className="text-sm leading-relaxed">
            The weight is {v("calibrate.weight.interior")}: {v("calibrate.weight.reason")}.
          </p>
          <table className="data-table mt-3 max-w-md">
            <thead>
              <tr>
                <th scope="col">Weight on the experiment</th>
                <th scope="col" className="num">
                  Residual against the experiment
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Half the stated weight</td>
                <td className="num">{v("calibrate.weight.residual_half")}</td>
              </tr>
              <tr>
                <td>The stated weight</td>
                <td className="num">{v("calibrate.weight.residual_one")}</td>
              </tr>
              <tr>
                <td>Twice the stated weight</td>
                <td className="num">{v("calibrate.weight.residual_double")}</td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs text-ink2 mt-3">{m.prov("calibrate.weight.residual_one")}</p>
        </div>
      </Section>

      <Section
        id="hillstrom"
        title="The Hillstrom email experiment"
        intro={
          <p>
            {v("data.hillstrom.rows")} recent customers of a catalog retailer, randomized to a men&apos;s merchandise email, a women&apos;s
            merchandise email or no email, with visits, conversions and spend tracked for {v("email.window_days")} days.
          </p>
        }
      >
        <Hillstrom text={text} />
      </Section>

      <Pushback>
        <p>
          The email test comes from a catalog retailer{year ? ` in ${year}` : ""}, so a CMO will ask why it belongs in a review of a direct
          to consumer brand today. Because it is the one real randomized result in the system: {v("data.hillstrom.rows")} customers split
          between the emails and no email, a sample ratio gate that passed at p = {v("email.srm_p")}, and outcomes nobody simulated.
        </p>
        <p>
          The uplift models on the targeting page are graded on it rather than on a simulation
          {learnersLost ? ", and on it they did not beat the simplest rule" : ""}. A result that holds on real customers is worth more than
          a better one on a market the build made up.
        </p>
      </Pushback>
    </>
  );
}
