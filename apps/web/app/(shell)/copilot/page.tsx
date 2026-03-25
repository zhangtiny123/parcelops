import { PageHeader } from "../../_components/page-header";
import { MetricCard } from "../../_components/ui";
import { getApiHealth, listHighSeverityIssues, makeApiUrl } from "../../_lib/api";
import { formatNumber, formatStatusLabel } from "../../_lib/format";

import { CopilotWorkspace } from "./copilot-workspace";

const starterPrompts = [
  {
    label: "Top recoveries",
    text: "Which open issues represent the highest recoverable amount right now?",
    note: "Ranks open issues by recoverable amount and cites the records returned.",
  },
  {
    label: "Spend shift",
    text: "Explain which providers have the sharpest recovery-cost increase this month.",
    note: "Compares current provider movement and calls out the biggest changes.",
  },
  {
    label: "High confidence",
    text: "Show the billing errors with the strongest confidence and the evidence behind them.",
    note: "Highlights the strongest billing anomalies and the evidence behind them.",
  },
];

export default async function CopilotPage() {
  const [healthResult, highSeverityResult] = await Promise.all([
    getApiHealth(),
    listHighSeverityIssues(5),
  ]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Copilot"
        title="Grounded analysis workspace"
        description="Ask grounded questions about recoverable issues, spend shifts, and billing anomalies. The default demo uses the built-in heuristic provider, so each answer stays tied to ParcelOps evidence without extra API-key setup."
      >
        <div className="page-action-row">
          <a
            className="button button-primary"
            href={makeApiUrl("/docs")}
            rel="noreferrer"
            target="_blank"
          >
            API docs
          </a>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Copilot readiness">
        <MetricCard
          detail={
            healthResult.error
              ? healthResult.error
              : `Environment ${formatStatusLabel(healthResult.data?.environment)}`
          }
          label="Copilot connection"
          tone={healthResult.data?.status === "ok" ? "good" : undefined}
          value={healthResult.data?.status === "ok" ? "Ready" : "Check API"}
        />
        <MetricCard
          detail="Top recoveries, spend increase analysis, and highest-confidence billing errors."
          label="Prompt starters"
          tone="accent"
          value={formatNumber(starterPrompts.length)}
        />
        <MetricCard
          detail={
            highSeverityResult.error
              ? highSeverityResult.error
              : "High-severity issues are ready to ground the first turns."
          }
          label="Grounding records"
          value={
            highSeverityResult.data
              ? formatNumber(highSeverityResult.data.length)
              : "Unavailable"
          }
        />
        <MetricCard
          detail="The current backend returns one complete grounded answer for each turn."
          label="Response mode"
          tone="warning"
          value="Request/response"
        />
      </section>

      <CopilotWorkspace
        apiHealthError={healthResult.error}
        initialHighSeverityIssues={highSeverityResult.data ?? []}
        initialHighSeverityIssuesError={highSeverityResult.error}
        isApiReady={healthResult.data?.status === "ok"}
        starterPrompts={starterPrompts}
      />
    </div>
  );
}
