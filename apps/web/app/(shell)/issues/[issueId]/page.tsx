import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../../_components/ui";
import { getIssue, makeApiUrl } from "../../../_lib/api";
import { formatCurrency, formatDateTime, formatPercent, formatStatusLabel } from "../../../_lib/format";
import {
  getIssueContextEntries,
  getReadableEvidenceEntries,
  readIssueFilters,
  stringifyIssueEvidence,
  toIssueSearchParams,
  type IssuePageSearchParams,
} from "../issue-utils";

type IssueDetailPageProps = {
  params: {
    issueId: string;
  };
  searchParams?: IssuePageSearchParams;
};

export default async function IssueDetailPage({
  params,
  searchParams,
}: IssueDetailPageProps) {
  const filters = readIssueFilters(searchParams);
  const backSearch = toIssueSearchParams(filters).toString();
  const backHref = backSearch ? `/issues?${backSearch}` : "/issues";
  const issueResult = await getIssue(params.issueId);

  if (!issueResult.data) {
    if (issueResult.status === 404) {
      notFound();
    }

    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Issues"
          title="Issue detail unavailable"
          description="The issue detail view could not be loaded from the backend."
        >
          <div className="page-action-row">
            <Link className="button button-secondary" href={backHref}>
              Back to issues
            </Link>
          </div>
        </PageHeader>

        <EmptyState
          description={issueResult.error ?? "Unable to load this issue."}
          title="Issue detail request failed."
          tone="danger"
        />
      </div>
    );
  }

  const issue = issueResult.data;
  const contextEntries = getIssueContextEntries(issue);
  const evidenceEntries = getReadableEvidenceEntries(issue);
  const rawEvidenceJson = stringifyIssueEvidence(issue);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Issues"
        title={formatStatusLabel(issue.issue_type)}
        description={issue.summary}
      >
        <div className="page-action-row">
          <Link className="button button-secondary" href={backHref}>
            Back to issues
          </Link>
          <a
            className="button button-primary"
            href={makeApiUrl(`/issues/${issue.id}`)}
            rel="noreferrer"
            target="_blank"
          >
            Raw issue API
          </a>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Issue detail metrics">
        <MetricCard
          detail="Estimated recoverable value currently attached to this issue."
          label="Recoverable amount"
          tone="accent"
          value={formatCurrency(issue.estimated_recoverable_amount)}
        />
        <MetricCard
          detail="Detection confidence recorded by the issue engine."
          label="Confidence"
          tone="good"
          value={formatPercent(issue.confidence)}
        />
        <MetricCard
          detail="Current severity and workflow status for the issue."
          label="Severity / status"
          tone="warning"
          value={`${formatStatusLabel(issue.severity)} / ${formatStatusLabel(issue.status)}`}
        />
        <MetricCard
          detail="Provider and timestamp for the most recent modeled detection."
          label="Detected"
          value={`${issue.provider_name} · ${formatDateTime(issue.detected_at)}`}
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-5"
          description="The core recovery posture attached to this anomaly."
          kicker="Summary"
          title="Issue assessment"
        >
          <div className="issue-summary-card">
            <div className="page-action-row">
              <StatusBadge label={formatStatusLabel(issue.issue_type)} />
              <StatusBadge label={formatStatusLabel(issue.severity)} />
              <StatusBadge label={formatStatusLabel(issue.status)} />
            </div>
            <p className="issue-summary-text">{issue.summary}</p>
            <div className="detail-grid">
              <div className="detail-item">
                <p className="status-label">Provider</p>
                <p className="detail-value">{issue.provider_name}</p>
              </div>
              <div className="detail-item">
                <p className="status-label">Issue ID</p>
                <p className="detail-value mono">{issue.id}</p>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          className="span-7"
          description="Shipment, invoice, and operational identifiers that anchor the issue to underlying records."
          kicker="Context"
          title="Linked records"
        >
          {contextEntries.length ? (
            <div className="detail-grid">
              {contextEntries.map((entry) => (
                <div className="detail-item" key={`${entry.label}:${entry.value}`}>
                  <p className="status-label">{entry.label}</p>
                  <p className="detail-value mono">{entry.value}</p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="This issue did not include shipment, invoice, or order identifiers beyond the summary text."
              title="No linked context was provided"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-12"
          description="Readable evidence fields make the anomaly understandable without forcing operators to parse raw JSON first."
          kicker="Evidence"
          title="Evidence snapshot"
        >
          {evidenceEntries.length ? (
            <div className="evidence-grid">
              {evidenceEntries.map((entry) => (
                <div className="detail-item" key={entry.key}>
                  <p className="status-label">{entry.label}</p>
                  <p className="detail-value">{entry.value}</p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="The issue model did not include structured evidence payload fields."
              title="No evidence fields were captured"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-12"
          description="Exact backend payload for auditing, debugging, or handing off to downstream workflows."
          kicker="JSON"
          title="Raw evidence payload"
        >
          <pre className="json-panel">
            <code>{rawEvidenceJson}</code>
          </pre>
        </SectionCard>
      </section>
    </div>
  );
}
