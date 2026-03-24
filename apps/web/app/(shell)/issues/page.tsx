import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import { getIssueDashboard, listIssues, makeApiUrl } from "../../_lib/api";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatStatusLabel,
} from "../../_lib/format";

export default async function IssuesPage() {
  const [dashboardResult, issuesResult] = await Promise.all([
    getIssueDashboard(),
    listIssues(),
  ]);

  const issues = issuesResult.data ?? [];
  const highestConfidenceIssue = [...issues].sort((left, right) => {
    const leftValue = typeof left.confidence === "number" ? left.confidence : Number(left.confidence ?? 0);
    const rightValue =
      typeof right.confidence === "number" ? right.confidence : Number(right.confidence ?? 0);

    return rightValue - leftValue;
  })[0];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Issues"
        title="Recovery issue register"
        description="Inspect anomalies, review severity, and validate where recoverable dollars are accumulating."
      >
        <div className="page-action-row">
          <a
            className="button button-primary"
            href={makeApiUrl("/issues")}
            rel="noreferrer"
            target="_blank"
          >
            Issues API
          </a>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Issue metrics">
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : "Total modeled recovery findings in the current summary window."
          }
          label="Total issues"
          tone="accent"
          value={
            dashboardResult.data
              ? formatNumber(dashboardResult.data.total_issue_count)
              : "Unavailable"
          }
        />
        <MetricCard
          detail="Estimated recoverable amount from the issue dashboard endpoint."
          label="Recoverable amount"
          tone="good"
          value={
            dashboardResult.data
              ? formatCurrency(dashboardResult.data.total_recoverable_amount)
              : "Unavailable"
          }
        />
        <MetricCard
          detail={
            issuesResult.error
              ? issuesResult.error
              : highestConfidenceIssue
              ? `${formatStatusLabel(highestConfidenceIssue.issue_type)} at ${formatPercent(
                  highestConfidenceIssue.confidence,
                )} confidence.`
              : "No confidence-scored issues yet."
          }
          label="Highest confidence"
          value={
            issuesResult.error
              ? "Unavailable"
              : highestConfidenceIssue
              ? formatPercent(highestConfidenceIssue.confidence)
              : "Unscored"
          }
        />
        <MetricCard
          detail="Distinct providers with active findings in the summary."
          label="Providers flagged"
          value={
            dashboardResult.data
              ? formatNumber(dashboardResult.data.issues_by_provider.length)
              : "Unavailable"
          }
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-4"
          description="Provider clusters from the issue dashboard summary."
          kicker="Distribution"
          title="Issues by provider"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Provider summary is unavailable."
              tone="danger"
            />
          ) : dashboardResult.data?.issues_by_provider.length ? (
            <div className="stack-list">
              {dashboardResult.data.issues_by_provider.slice(0, 5).map((provider) => (
                <div className="list-row" key={provider.provider_name}>
                  <div className="list-row-main">
                    <p className="list-row-title">{provider.provider_name}</p>
                    <p className="list-row-detail">
                      {formatNumber(provider.count)} linked issues
                    </p>
                  </div>
                  <p className="list-row-value">
                    {formatCurrency(provider.estimated_recoverable_amount)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="Run issue detection to populate provider-level rollups."
              title="No provider distribution yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-8"
          description="A clean register of findings that later tasks will extend with filters and detail views."
          kicker="Register"
          title="Recent issues"
        >
          {issuesResult.error ? (
            <EmptyState
              description={issuesResult.error}
              title="Issue records could not be loaded."
              tone="danger"
            />
          ) : issues.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Amount</th>
                    <th>Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.slice(0, 12).map((issue) => (
                    <tr key={issue.id}>
                      <td>
                        <strong>{formatStatusLabel(issue.issue_type)}</strong>
                        <span className="table-note">{issue.summary}</span>
                      </td>
                      <td>{issue.provider_name}</td>
                      <td>
                        <StatusBadge label={formatStatusLabel(issue.status)} />
                      </td>
                      <td>{formatPercent(issue.confidence)}</td>
                      <td>{formatCurrency(issue.estimated_recoverable_amount)}</td>
                      <td>{formatDateTime(issue.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="This register will populate as soon as the backend has modeled recovery issues."
              title="No issues detected yet"
            />
          )}
        </SectionCard>
      </section>
    </div>
  );
}
