import Link from "next/link";

import { PageHeader } from "../../_components/page-header";
import {
  EmptyState,
  MetricCard,
  SectionCard,
  StatusBadge,
} from "../../_components/ui";
import {
  getApiHealth,
  getIssueDashboard,
  listHighSeverityIssues,
  listUploads,
  makeApiUrl,
} from "../../_lib/api";
import {
  formatBytes,
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatStatusLabel,
} from "../../_lib/format";

export default async function DashboardPage() {
  const [healthResult, dashboardResult, issuesResult, uploadsResult] =
    await Promise.all([
      getApiHealth(),
      getIssueDashboard(),
      listHighSeverityIssues(5),
      listUploads(),
    ]);

  const latestUpload = uploadsResult.data?.[0] ?? null;
  const topProvider = dashboardResult.data?.issues_by_provider[0] ?? null;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Dashboard"
        title="Recovery operations overview"
        description="Review the current ingest lane, issue pressure, and backend readiness from a single operator shell."
      >
        <div className="page-action-row">
          <Link className="button button-secondary" href="/issues">
            Review issues
          </Link>
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

      <section className="metric-grid" aria-label="Dashboard metrics">
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : `${formatNumber(
                  dashboardResult.data?.total_issue_count ?? 0,
                )} modeled issues in the last 30 days.`
          }
          label="Recoverable amount"
          tone="accent"
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
              : issuesResult.data?.length
                ? "Highest-severity anomalies are ready for analyst review."
                : "No high-severity anomalies are currently flagged."
          }
          label="High-severity queue"
          tone="warning"
          value={
            issuesResult.data ? formatNumber(issuesResult.data.length) : "Unavailable"
          }
        />
        <MetricCard
          detail={
            uploadsResult.error
              ? uploadsResult.error
              : latestUpload
                ? `${latestUpload.original_filename} · ${formatStatusLabel(
                    latestUpload.status,
                  )}`
                : "No uploads are registered yet."
          }
          label="Uploads tracked"
          value={
            uploadsResult.data ? formatNumber(uploadsResult.data.length) : "Unavailable"
          }
        />
        <MetricCard
          detail={
            healthResult.error
              ? healthResult.error
              : `Storage root ${healthResult.data?.storage_root}`
          }
          label="API status"
          tone={healthResult.data?.status === "ok" ? "good" : undefined}
          value={healthResult.data?.status === "ok" ? "Connected" : "Offline"}
        />
      </section>

      <section className="content-grid content-grid--wide">
        <SectionCard
          className="span-4"
          description="Where recoverable dollars are clustering right now."
          kicker="Issue mix"
          title="Top issue types"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Issue summary is unavailable."
              tone="danger"
            />
          ) : dashboardResult.data?.issues_by_type.length ? (
            <div className="stack-list">
              {dashboardResult.data.issues_by_type.slice(0, 5).map((metric) => (
                <div className="list-row" key={metric.issue_type}>
                  <div className="list-row-main">
                    <p className="list-row-title">
                      {formatStatusLabel(metric.issue_type)}
                    </p>
                    <p className="list-row-detail">
                      {formatNumber(metric.count)} open findings in the modeled
                      period.
                    </p>
                  </div>
                  <p className="list-row-value">
                    {formatCurrency(metric.estimated_recoverable_amount)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="Issue detection has not produced recoverable findings yet."
              title="No issue metrics yet"
            />
          )}
        </SectionCard>

        <SectionCard
          action={<Link className="button button-secondary" href="/uploads">Open uploads</Link>}
          className="span-5"
          description="Most recent tracked files and normalization posture."
          kicker="Intake"
          title="Latest uploads"
        >
          {uploadsResult.error ? (
            <EmptyState
              description={uploadsResult.error}
              title="Upload data is unavailable."
              tone="danger"
            />
          ) : uploadsResult.data?.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Rows</th>
                    <th>Uploaded</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadsResult.data.slice(0, 6).map((upload) => (
                    <tr key={upload.id}>
                      <td>
                        <strong>{upload.original_filename}</strong>
                        <span className="table-note">
                          {upload.source_kind
                            ? formatStatusLabel(upload.source_kind)
                            : "Source kind pending"}
                        </span>
                      </td>
                      <td>
                        <StatusBadge label={formatStatusLabel(upload.status)} />
                      </td>
                      <td>{formatNumber(upload.normalized_row_count)}</td>
                      <td>{formatDateTime(upload.uploaded_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="Task 10 will add browser file submission, preview, and mapping from this lane."
              title="No uploads have been registered"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-3"
          description="Runtime dependencies and storage configuration from the backend."
          kicker="Health"
          title="System readiness"
        >
          {healthResult.error ? (
            <EmptyState
              description={healthResult.error}
              title="The API is unreachable."
              tone="danger"
            />
          ) : (
            <div className="detail-grid">
              <div className="detail-item">
                <p className="status-label">Environment</p>
                <p className="detail-value">
                  {formatStatusLabel(healthResult.data?.environment)}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Max upload size</p>
                <p className="detail-value">
                  {formatBytes(healthResult.data?.max_upload_size_bytes ?? 0)}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Postgres</p>
                <p className="detail-value">
                  {healthResult.data?.dependencies.postgres_host}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Redis</p>
                <p className="detail-value">
                  {healthResult.data?.dependencies.redis_host}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Leading provider</p>
                <p className="detail-value">
                  {topProvider
                    ? `${topProvider.provider_name} (${formatNumber(
                        topProvider.count,
                      )})`
                    : "No provider trend yet"}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Storage root</p>
                <p className="detail-value">
                  <code>{healthResult.data?.storage_root}</code>
                </p>
              </div>
            </div>
          )}
        </SectionCard>
      </section>
    </div>
  );
}
