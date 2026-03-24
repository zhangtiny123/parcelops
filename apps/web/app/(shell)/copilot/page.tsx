import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import { getApiHealth, getApiMeta, listHighSeverityIssues, makeApiUrl } from "../../_lib/api";
import { formatNumber, formatStatusLabel } from "../../_lib/format";

const starterPrompts = [
  {
    label: "Top recoveries",
    text: "Which open issues represent the highest recoverable amount right now?",
    note: "Will cite issue IDs and amounts when the chat layer ships.",
  },
  {
    label: "Spend shift",
    text: "Explain which providers have the sharpest recovery-cost increase this month.",
    note: "Will lean on dashboard trends and provider groupings.",
  },
  {
    label: "High confidence",
    text: "Show the billing errors with the strongest confidence and the evidence behind them.",
    note: "Will surface issue summaries and supporting evidence payloads.",
  },
];

export default async function CopilotPage() {
  const [metaResult, healthResult, highSeverityResult] = await Promise.all([
    getApiMeta(),
    getApiHealth(),
    listHighSeverityIssues(3),
  ]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Copilot"
        title="Grounded analysis workspace"
        description="The chat surface is not active yet, but the route is in place and already wired to the same issue and health context the assistant will use."
      >
        <div className="page-action-row">
          <a
            className="button button-primary"
            href={makeApiUrl("/docs")}
            rel="noreferrer"
            target="_blank"
          >
            Backend surface
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
          label="API connection"
          tone={healthResult.data?.status === "ok" ? "good" : undefined}
          value={healthResult.data?.status === "ok" ? "Ready" : "Offline"}
        />
        <MetricCard
          detail="Starter prompts staged for the future chat interface."
          label="Prompt starters"
          tone="accent"
          value={formatNumber(starterPrompts.length)}
        />
        <MetricCard
          detail="Current high-severity findings available for grounding."
          label="Issue references"
          value={
            highSeverityResult.data
              ? formatNumber(highSeverityResult.data.length)
              : "Unavailable"
          }
        />
        <MetricCard
          detail="Backend root endpoint confirms discoverable service links."
          label="Service discovery"
          value={metaResult.data?.service === "api" ? "Linked" : "Unknown"}
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-7"
          description="Prompt scaffolding is visible now so the future chat surface arrives in an already-familiar workspace."
          kicker="Prompts"
          title="Starter prompts"
        >
          <div className="prompt-grid">
            {starterPrompts.map((prompt) => (
              <article className="prompt-card" key={prompt.label}>
                <span className="prompt-label">{prompt.label}</span>
                <p className="prompt-text">{prompt.text}</p>
                <p className="prompt-note">{prompt.note}</p>
                <StatusBadge label="Planned" tone="muted" />
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          className="span-5"
          description="Evidence sources the future copilot can cite."
          kicker="Grounding"
          title="Available context"
        >
          {highSeverityResult.error ? (
            <EmptyState
              description={highSeverityResult.error}
              title="Issue context could not be loaded."
              tone="danger"
            />
          ) : highSeverityResult.data?.length ? (
            <div className="stack-list">
              {highSeverityResult.data.map((issue) => (
                <div className="list-row" key={issue.id}>
                  <div className="list-row-main">
                    <p className="list-row-title">{formatStatusLabel(issue.issue_type)}</p>
                    <p className="list-row-detail">{issue.summary}</p>
                  </div>
                  <StatusBadge label={issue.id.slice(0, 8)} tone="muted" />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="Once issues exist, the copilot will be able to ground responses in real anomaly records."
              title="No issue references yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-12"
          description="Task 14 adds the actual message transport and cited responses."
          kicker="Status"
          title="Copilot route placeholder"
        >
          <EmptyState
            action={
              metaResult.data ? (
                <a
                  className="button button-secondary"
                  href={makeApiUrl(metaResult.data.docs_url)}
                  rel="noreferrer"
                  target="_blank"
                >
                  Inspect current API docs
                </a>
              ) : undefined
            }
            description="This page is intentionally restrained: it establishes navigation, layout, and grounding context without pretending the chat workflow already exists."
            title="Chat transport is not implemented yet"
          />
        </SectionCard>
      </section>
    </div>
  );
}
