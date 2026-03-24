import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import { listUploads, makeApiUrl } from "../../_lib/api";
import {
  formatDateTime,
  formatNumber,
  formatStatusLabel,
} from "../../_lib/format";

function buildStatusCounts(statuses: string[]) {
  return statuses.reduce<Record<string, number>>((counts, status) => {
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
}

export default async function UploadsPage() {
  const uploadsResult = await listUploads();
  const statusCounts = buildStatusCounts(
    uploadsResult.data?.map((upload) => upload.status) ?? [],
  );

  const completedCount =
    (statusCounts.normalized ?? 0) + (statusCounts.normalized_with_errors ?? 0);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Uploads"
        title="Ingestion lane"
        description="Track source files, mapping readiness, and normalization progress before data lands in the modeled tables."
      >
        <div className="page-action-row">
          <a
            className="button button-primary"
            href={makeApiUrl("/uploads")}
            rel="noreferrer"
            target="_blank"
          >
            Uploads API
          </a>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Upload metrics">
        <MetricCard
          detail={
            uploadsResult.error
              ? uploadsResult.error
              : "Tracked files currently registered with the backend."
          }
          label="Registered files"
          tone="accent"
          value={
            uploadsResult.data ? formatNumber(uploadsResult.data.length) : "Unavailable"
          }
        />
        <MetricCard
          detail="Files mapped and ready for a normalization run."
          label="Ready to normalize"
          tone="good"
          value={
            uploadsResult.data ? formatNumber(statusCounts.mapped ?? 0) : "Unavailable"
          }
        />
        <MetricCard
          detail="Files that completed normalization, including partial-error runs."
          label="Completed"
          value={uploadsResult.data ? formatNumber(completedCount) : "Unavailable"}
        />
        <MetricCard
          detail="Queued, running, or failed normalization jobs needing attention."
          label="Watchlist"
          tone="warning"
          value={
            uploadsResult.data
              ? formatNumber(
                  (statusCounts.normalization_queued ?? 0) +
                    (statusCounts.normalizing ?? 0) +
                    (statusCounts.normalization_failed ?? 0),
                )
              : "Unavailable"
          }
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-8"
          description="Recent source files and the latest backend status for each one."
          kicker="Queue"
          title="Tracked uploads"
        >
          {uploadsResult.error ? (
            <EmptyState
              description={uploadsResult.error}
              title="Uploads could not be loaded."
              tone="danger"
            />
          ) : uploadsResult.data?.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Rows normalized</th>
                    <th>Errors</th>
                    <th>Uploaded</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadsResult.data.map((upload) => (
                    <tr key={upload.id}>
                      <td>
                        <strong>{upload.original_filename}</strong>
                        <span className="table-note mono">{upload.id}</span>
                      </td>
                      <td>
                        {upload.source_kind
                          ? formatStatusLabel(upload.source_kind)
                          : formatStatusLabel(upload.file_type)}
                      </td>
                      <td>
                        <StatusBadge label={formatStatusLabel(upload.status)} />
                      </td>
                      <td>{formatNumber(upload.normalized_row_count)}</td>
                      <td>{formatNumber(upload.normalization_error_count)}</td>
                      <td>{formatDateTime(upload.uploaded_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="The intake shell is ready, but browser-side file submission and preview arrive in Task 10."
              title="No uploads yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-4"
          description="What this route is preparing for next."
          kicker="Next"
          title="Workflow handoff"
        >
          <div className="stack-list">
            <div className="list-row">
              <div className="list-row-main">
                <p className="list-row-title">Upload and preview</p>
                <p className="list-row-detail">
                  Browser file submission will attach directly to the existing
                  `POST /uploads` endpoint.
                </p>
              </div>
            </div>
            <div className="list-row">
              <div className="list-row-main">
                <p className="list-row-title">Schema mapping</p>
                <p className="list-row-detail">
                  Suggested mappings and operator edits will use the upload
                  preview and mapping endpoints already exposed by the API.
                </p>
              </div>
            </div>
            <div className="list-row">
              <div className="list-row-main">
                <p className="list-row-title">Normalization control</p>
                <p className="list-row-detail">
                  Triggering normalization and surfacing row-level errors land in
                  the next UI task.
                </p>
              </div>
            </div>
          </div>
        </SectionCard>
      </section>
    </div>
  );
}
