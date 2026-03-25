import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "../../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../../_components/ui";
import { getCase, makeApiUrl } from "../../../_lib/api";
import { formatCurrency, formatDateTime, formatNumber, formatStatusLabel } from "../../../_lib/format";
import { updateRecoveryCaseAction } from "../actions";

type CaseDetailPageProps = {
  params: {
    caseId: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
};

function getSearchParamValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function CaseDetailPage({
  params,
  searchParams,
}: CaseDetailPageProps) {
  const caseResult = await getCase(params.caseId);

  if (!caseResult.data) {
    if (caseResult.status === 404) {
      notFound();
    }

    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Cases"
          title="Recovery case unavailable"
          description="The recovery case detail view could not be loaded from the backend."
        >
          <div className="page-action-row">
            <Link className="button button-secondary" href="/cases">
              Back to cases
            </Link>
          </div>
        </PageHeader>

        <EmptyState
          description={caseResult.error ?? "Unable to load this recovery case."}
          title="Recovery case request failed."
          tone="danger"
        />
      </div>
    );
  }

  const recoveryCase = caseResult.data;
  const notice = getSearchParamValue(searchParams?.notice);
  const error = getSearchParamValue(searchParams?.error);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Cases"
        title={recoveryCase.title}
        description="Review the linked issues, refine the generated dispute drafts, and keep the recovery workflow status current."
      >
        <div className="page-action-row">
          <Link className="button button-secondary" href="/cases">
            Back to cases
          </Link>
          <a
            className="button button-primary"
            href={makeApiUrl(`/cases/${recoveryCase.id}`)}
            rel="noreferrer"
            target="_blank"
          >
            Raw case API
          </a>
        </div>
      </PageHeader>

      {notice ? (
        <div className="inline-notice inline-notice--good" role="status">
          {notice}
        </div>
      ) : null}

      {error ? (
        <div className="inline-notice inline-notice--danger" role="status">
          {error}
        </div>
      ) : null}

      <section className="metric-grid" aria-label="Recovery case metrics">
        <MetricCard
          detail="Current workflow status for this recovery case."
          label="Case status"
          tone="accent"
          value={formatStatusLabel(recoveryCase.status)}
        />
        <MetricCard
          detail="Recovery issues currently grouped into this case."
          label="Linked issues"
          tone="warning"
          value={formatNumber(recoveryCase.issue_count)}
        />
        <MetricCard
          detail="Estimated recoverable value represented by the linked issues."
          label="Recoverable amount"
          tone="good"
          value={formatCurrency(recoveryCase.estimated_recoverable_amount)}
        />
        <MetricCard
          detail="Most recent saved change to the case record."
          label="Updated"
          value={formatDateTime(recoveryCase.updated_at)}
        />
      </section>

      <section className="content-grid">
        <SectionCard
          className="span-12"
          description="Operators can edit the title, status, and generated dispute drafts without breaking the linkage back to the underlying issues."
          kicker="Workflow"
          title="Case details"
        >
          <form action={updateRecoveryCaseAction} className="case-editor">
            <input name="case_id" type="hidden" value={recoveryCase.id} />

            <div className="detail-grid">
              <div className="detail-item">
                <p className="status-label">Case ID</p>
                <p className="detail-value mono">{recoveryCase.id}</p>
              </div>
              <div className="detail-item">
                <p className="status-label">Created</p>
                <p className="detail-value">{formatDateTime(recoveryCase.created_at)}</p>
              </div>
              <div className="detail-item">
                <p className="status-label">Current status</p>
                <div className="page-action-row">
                  <StatusBadge label={formatStatusLabel(recoveryCase.status)} />
                </div>
              </div>
            </div>

            <div className="case-editor-grid">
              <label className="field-group">
                <span className="field-label">Title</span>
                <input
                  className="field-input"
                  defaultValue={recoveryCase.title}
                  name="title"
                  required
                  type="text"
                />
              </label>

              <label className="field-group">
                <span className="field-label">Status</span>
                <select
                  className="field-select"
                  defaultValue={recoveryCase.status}
                  name="status"
                >
                  <option value="open">Open</option>
                  <option value="pending">Pending</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
            </div>

            <label className="field-group">
              <span className="field-label">Draft summary</span>
              <textarea
                className="field-input field-textarea"
                defaultValue={recoveryCase.draft_summary ?? ""}
                name="draft_summary"
                rows={8}
              />
            </label>

            <label className="field-group">
              <span className="field-label">Draft email</span>
              <textarea
                className="field-input field-textarea"
                defaultValue={recoveryCase.draft_email ?? ""}
                name="draft_email"
                rows={12}
              />
            </label>

            <div className="button-row">
              <button className="button button-primary" type="submit">
                Save case
              </button>
            </div>
          </form>
        </SectionCard>

        <SectionCard
          className="span-12"
          description="These linked issues remain the evidence basis for the case. Open any issue to inspect its full recovery context and raw payload."
          kicker="Linked issues"
          title="Case evidence set"
        >
          {recoveryCase.issues.length ? (
            <div className="stack-list">
              {recoveryCase.issues.map((issue) => (
                <div className="list-row" key={issue.id}>
                  <div className="list-row-main">
                    <Link className="table-link-button" href={`/issues/${issue.id}`}>
                      <span className="table-link-title">
                        {formatStatusLabel(issue.issue_type)}
                      </span>
                      <span className="table-note">{issue.summary}</span>
                    </Link>

                    <div className="page-action-row">
                      <StatusBadge label={issue.provider_name} />
                      <StatusBadge label={formatStatusLabel(issue.severity)} />
                      <StatusBadge label={formatStatusLabel(issue.status)} />
                    </div>

                    <p className="list-row-detail">
                      Detected {formatDateTime(issue.detected_at)} and linked to this case
                      for operator follow-up.
                    </p>
                  </div>

                  <div className="list-row-main">
                    <p className="list-row-value">
                      {formatCurrency(issue.estimated_recoverable_amount)}
                    </p>
                    <p className="list-row-detail mono">{issue.id}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              description="This case does not currently have any linked issues."
              title="No issues are attached"
            />
          )}
        </SectionCard>
      </section>
    </div>
  );
}
