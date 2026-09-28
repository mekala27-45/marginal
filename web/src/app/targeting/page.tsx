import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DataTable } from "@/components/charts/ChartFrame";
import { PageHeader, Pushback } from "@/components/Section";
import { formatValue, type Scalar } from "@/lib/format";
import { manifest } from "@/lib/load";
import type { ManifestView } from "@/lib/manifest";

import { type Dataset, TargetingClient, type TargetingText } from "./TargetingClient";

export const metadata: Metadata = { title: "Targeting" };

function qiniText(m: ManifestView, d: Dataset, policy: string): string {
  return `${m.v(`targeting.${d}.${policy}.qini`)} (${m.v(`targeting.${d}.${policy}.qini_lower`)} to ${m.v(`targeting.${d}.${policy}.qini_upper`)})`;
}

function tableOf(m: ManifestView, key: string) {
  const t = m.table(key);
  return { columns: t.columns, formats: t.formats, rows: t.rows };
}

export default function Targeting() {
  const m = manifest();
  const v = (key: string) => m.v(key);
  const pv = (d: string, p: string) => m.num(`targeting.${d}.${p}.policy_value_test`);
  const includesZero = (d: string, p: string) =>
    m.num(`targeting.${d}.${p}.qini_lower`) <= 0 && m.num(`targeting.${d}.${p}.qini_upper`) >= 0;
  const clearOfZero = (d: string, p: string) => m.num(`targeting.${d}.${p}.qini_lower`) > 0;

  const learnersLost =
    pv("hillstrom", "t_learner") < pv("hillstrom", "sure_things") && pv("hillstrom", "x_learner") < pv("hillstrom", "sure_things");
  const hillstromZero = ["t_learner", "x_learner", "sure_things"].every((p) => includesZero("hillstrom", p));
  const criteoClear = ["t_learner", "x_learner", "sure_things"].every((p) => clearOfZero("criteo", p));
  const simRuleBelow = m.num("targeting.sim.sure_things.qini_upper") < 0;
  const hillstromDiff = m.table("targeting.hillstrom.qini_differences").rows.find((r) => String(r[0]).includes("Sure things"));

  const text: TargetingText = {
    level: v("targeting.level"),
    datasets: {
      hillstrom: {
        tab: "Hillstrom email (real)",
        qiniUnit: "Incremental conversions per thousand on the list",
        lead: `On this dataset's test split the uplift learners ${learnersLost ? "did not beat" : "beat"} the sure things rule. Per thousand customers on the list, the T learner makes ${v("targeting.hillstrom.t_learner.policy_value_test")} and the X learner ${v("targeting.hillstrom.x_learner.policy_value_test")}, against ${v("targeting.hillstrom.sure_things.policy_value_test")} for the sure things rule and ${v("targeting.hillstrom.everyone.policy_value_test")} for emailing everyone. The Qini coefficients, ${qiniText(m, "hillstrom", "t_learner")} for the T learner against ${qiniText(m, "hillstrom", "sure_things")} for sure things, ${hillstromZero ? "have intervals that include zero" : "differ"}.`,
        qini: {
          callout: `Qini coefficients of ${qiniText(m, "hillstrom", "t_learner")} for the T learner, ${qiniText(m, "hillstrom", "x_learner")} for the X learner and ${qiniText(m, "hillstrom", "sure_things")} for the sure things rule. ${hillstromZero ? "Every interval includes zero, so on this test split no policy ranks customers by their response to the email better than chance." : ""}`,
          provenance: m.prov("targeting.hillstrom.policies"),
        },
        value: {
          callout: `On the test split the sure things rule, contacting ${v("targeting.hillstrom.sure_things.chosen_share")} of the list, makes ${v("targeting.hillstrom.sure_things.policy_value_test")} per thousand customers, against ${v("targeting.hillstrom.t_learner.policy_value_test")} for the T learner at ${v("targeting.hillstrom.t_learner.chosen_share")} and ${v("targeting.hillstrom.everyone.policy_value_test")} for emailing everyone.`,
          costs: `Each email costs ${v("targeting.hillstrom.cost_per_contact")}; spend counts at a ${v("targeting.hillstrom.margin_on_spend")} margin.`,
          fmt: "usd0",
          unit: v("targeting.hillstrom.value_unit"),
          provenance: m.prov("targeting.hillstrom.sure_things.policy_value_test"),
        },
        summaryProvenance: m.prov("targeting.hillstrom.policies"),
      },
      sim: {
        tab: "Simulated customers (known truth)",
        qiniUnit: "Incremental conversions per thousand on the list",
        lead: `With effects the simulator knows, the learners find the customers the email persuades. The X learner's Qini coefficient is ${qiniText(m, "sim", "x_learner")} and the T learner's ${qiniText(m, "sim", "t_learner")}; the sure things rule scores ${qiniText(m, "sim", "sure_things")}${simRuleBelow ? ", below zero" : ""}. Against an oracle that contacts exactly the persuadables, the X learner gives up ${v("targeting.sim.regret.x_learner")} conversions on the test split and the T learner ${v("targeting.sim.regret.t_learner")}, where contacting everyone gives up ${v("targeting.sim.regret.everyone")}.`,
        qini: {
          callout: `The X learner's Qini coefficient is ${qiniText(m, "sim", "x_learner")} and the T learner's ${qiniText(m, "sim", "t_learner")}, both well above zero; the sure things rule's is ${qiniText(m, "sim", "sure_things")}. Their error in each customer's effect (PEHE) is ${v("targeting.sim.pehe.x_learner")} for the X learner and ${v("targeting.sim.pehe.t_learner")} for the T learner.`,
          provenance: m.prov("targeting.sim.policies"),
        },
        value: {
          callout: `Contacting the share chosen on validation, the X learner makes ${v("targeting.sim.x_learner.policy_value_test")} per thousand on the test split at ${v("targeting.sim.x_learner.chosen_share")} and the T learner ${v("targeting.sim.t_learner.policy_value_test")} at ${v("targeting.sim.t_learner.chosen_share")}, against ${v("targeting.sim.everyone.policy_value_test")} for contacting everyone.`,
          costs: `Each contact costs ${v("targeting.sim.cost_per_contact")}; a conversion is worth ${v("targeting.sim.revenue_per_conversion")} at a ${v("targeting.sim.margin")} margin.`,
          fmt: "usd0",
          unit: v("targeting.sim.value_unit"),
          provenance: m.prov("targeting.sim.x_learner.policy_value_test"),
        },
        summaryProvenance: m.prov("targeting.sim.policies"),
      },
      criteo: {
        tab: "Criteo (real, full release)",
        qiniUnit: "Incremental visits per thousand on the list",
        lead: `The release that ran is the full Criteo file, ${v("targeting.criteo.rows_total")} rows. Models were fit on a seeded ${v("targeting.criteo.rows_train_used")} of ${v("targeting.criteo.rows_train")} training rows, shares were chosen on ${v("targeting.criteo.rows_validation")} and the policies scored on ${v("targeting.criteo.rows_test")}, in ${v("targeting.criteo.seconds")} seconds against a budget of ${v("targeting.criteo.budget_seconds")}. The outcome is the ${v("targeting.criteo.outcome")}; ${v("targeting.criteo.learners")}.`,
        qini: {
          callout: `On the full release ${criteoClear ? "every targeting policy beats random with an interval clear of zero" : "the policies separate from random"}: ${qiniText(m, "criteo", "x_learner")} for the X learner, ${qiniText(m, "criteo", "sure_things")} for the sure things rule and ${qiniText(m, "criteo", "t_learner")} for the T learner.`,
          provenance: m.prov("targeting.criteo.policies"),
        },
        value: {
          callout: `Contacting the share chosen on validation, the sure things rule at ${v("targeting.criteo.sure_things.chosen_share")} makes ${v("targeting.criteo.sure_things.policy_value_test")} per thousand users on the list, against ${v("targeting.criteo.everyone.policy_value_test")} for everyone; both learners chose ${v("targeting.criteo.t_learner.chosen_share")}, the edge of the grid.`,
          costs: `Values are ${v("targeting.criteo.value_unit")}.`,
          fmt: "float1",
          unit: m.text("targeting.criteo.value_unit").split(";")[0] ?? "",
          provenance: m.prov("targeting.criteo.sure_things.policy_value_test"),
        },
        summaryProvenance: m.prov("targeting.criteo.policies"),
      },
    },
    quadrants: {
      callout: `The X learner contacts ${v("targeting.sim.quadrant.x_learner.persuadable")} of the persuadables and ${v("targeting.sim.quadrant.x_learner.sleeping_dog")} of the sleeping dogs; the T learner ${v("targeting.sim.quadrant.t_learner.persuadable")} and ${v("targeting.sim.quadrant.t_learner.sleeping_dog")}. Contacting everyone reaches ${v("targeting.sim.quadrant.everyone.persuadable")} of the persuadables and ${v("targeting.sim.quadrant.everyone.sleeping_dog")} of the sleeping dogs.`,
      provenance: m.prov("targeting.sim.quadrants"),
      labels: { persuadable: "Persuadables", sure_thing: "Sure things", lost_cause: "Lost causes", sleeping_dog: "Sleeping dogs" },
    },
  };

  const extra: Record<Dataset, ReactNode> = {
    hillstrom: (
      <div key="hillstrom" className="card p-4 sm:p-5 mt-5 max-w-3xl">
        <h3 className="font-sans text-[0.95rem] font-semibold mb-2">Paired differences in the Qini coefficient</h3>
        <DataTable table={tableOf(m, "targeting.hillstrom.qini_differences")} dense={false} caption="Paired bootstrap on the test split" />
        <p className="text-xs text-ink2 mt-3">{m.prov("targeting.hillstrom.qini_differences")}</p>
      </div>
    ),
    sim: (
      <div key="sim" className="card p-4 sm:p-5 mt-5 max-w-3xl" data-testid="oracle-figures">
        <h3 className="font-sans text-[0.95rem] font-semibold mb-2">How close each policy comes to the oracle</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Policy</th>
              <th scope="col" className="num">
                Error in each customer&apos;s effect (PEHE)
              </th>
              <th scope="col" className="num">
                Conversions given up against the oracle
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>T learner</td>
              <td className="num">{v("targeting.sim.pehe.t_learner")}</td>
              <td className="num">{v("targeting.sim.regret.t_learner")}</td>
            </tr>
            <tr>
              <td>X learner</td>
              <td className="num">{v("targeting.sim.pehe.x_learner")}</td>
              <td className="num">{v("targeting.sim.regret.x_learner")}</td>
            </tr>
            <tr>
              <td>Sure things</td>
              <td className="num text-ink2">not a model</td>
              <td className="num">{v("targeting.sim.regret.sure_things")}</td>
            </tr>
            <tr>
              <td>Everyone</td>
              <td className="num text-ink2">not a model</td>
              <td className="num">{v("targeting.sim.regret.everyone")}</td>
            </tr>
          </tbody>
        </table>
        <p className="text-xs text-ink2 mt-3">
          The oracle contacts the {v("targeting.sim.test_quadrant_share.persuadable")} of test customers who are persuadables and converts{" "}
          {v("targeting.sim.oracle_conversions")} more of them. {m.prov("targeting.sim.regret.x_learner")}
        </p>
      </div>
    ),
    criteo: (
      <div key="criteo" className="card p-4 sm:p-5 mt-5 max-w-3xl text-sm space-y-2" data-testid="criteo-release">
        <h3 className="font-sans text-[0.95rem] font-semibold">The release that ran</h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-ink2">File</dt>
          <dd className="mono text-xs break-all">{v("data.criteo.url")}</dd>
          <dt className="text-ink2">Rows</dt>
          <dd className="num">{v("data.criteo.rows")}</dd>
          <dt className="text-ink2">Published MD5</dt>
          <dd className="mono text-xs break-all">{v("data.criteo.md5")}</dd>
          <dt className="text-ink2">Treated share</dt>
          <dd className="num">{v("data.criteo.treated_share")}</dd>
          <dt className="text-ink2">Visit rate</dt>
          <dd className="num">{v("data.criteo.visit_rate")}</dd>
          <dt className="text-ink2">Licence</dt>
          <dd>{v("data.criteo.license")}</dd>
        </dl>
        <p className="text-xs text-ink2">{v("data.criteo.citation")}</p>
      </div>
    ),
  };

  return (
    <>
      <PageHeader kicker="Targeting" question="Who should get the email, and does a model know better than a rule?">
        <p>
          The uplift learners, a T learner and an X learner, are set against a sure things rule and against emailing everyone, on a real
          randomized email test, on simulated customers whose response is known, and on Criteo&apos;s public uplift release. Each policy
          chooses how much of the list to contact on a validation split and is scored on a test split it never saw.
        </p>
      </PageHeader>
      <TargetingClient text={text} extra={extra} />
      <Pushback>
        <p>
          The uplift model lost to the sure things rule on the real test, so a CMO will ask why run one. Because on that test the intervals
          include zero: the T learner&apos;s Qini of {v("targeting.hillstrom.t_learner.qini")} and the sure things rule&apos;s{" "}
          {v("targeting.hillstrom.sure_things.qini")} cannot be told apart
          {hillstromDiff ? ` (a paired difference of ${formatDiff(hillstromDiff)})` : ""}.
        </p>
        <p>
          On the simulator, where the effects are known, the learners win clearly: the X learner&apos;s Qini is{" "}
          {v("targeting.sim.x_learner.qini")} against the rule&apos;s {v("targeting.sim.sure_things.qini")}. The policy value curve is the
          tool that says which case a real list is in: it picks the share to contact on validation and reports the value on a test split
          nobody tuned on.
        </p>
      </Pushback>
    </>
  );
}

function formatDiff(row: Scalar[]): string {
  return `${formatValue(row[1] ?? null, "float3")}, interval ${formatValue(row[2] ?? null, "float3")} to ${formatValue(row[3] ?? null, "float3")}`;
}
