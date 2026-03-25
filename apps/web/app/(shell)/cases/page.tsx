import Link from "next/link";

import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import { getIssueDashboard, listCases, makeApiUrl } from "../../_lib/api";
import type { RecoveryCaseListItem, RecoveryCaseStatus } from "../../_lib/api-types";
import { formatCurrency, formatDateTime, formatNumber, formatStatusLabel } from "../../_lib/format";

type CasesPageProps = {
  searchParams?: Record<string, string | string[] | undefined>;
};

function getSearchParamValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function getCaseStatusCount(
  cases: RecoveryCaseListItem[],
  status: RecoveryCaseStatus,
) {
  return cases.filter((recoveryCase) => recoveryCase.status === status).length;
}

export default async function CasesPage({ searchParams }: CasesPageProps) {
  const [dashboardResult, casesResult] = await Promise.all([
    getIssueDashboard(),
    listCases(),
  ]);

  const recoveryCases = casesResult.data ?? [];
  const notice = getSearchParamValue(searchParams?.notice);
  const error = getSearchParamValue(searchParams?.error);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Cases"
        title="Recovery case register"
        description="Turn issue findings into dispute-ready recovery cases, keep editable operator drafts in one place, and track each case through open, pending, and resolved stages."
      >
        <div className="page-action-row">
          <Link className="button button-secondary" href="/issues">
            Create from issues
          </Link>
          <a
            className="button button-primary"
            href={makeApiUrl("/cases")}
            rel="noreferrer"
            target="_blank"
          >
            Cases API
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

      <section className="metric-grid" aria-label="Case register metrics">
        <MetricCard
          detail={
            casesResult.error
              ? casesResult.error
              : "Cases currently persisted in the recovery workflow."
          }
          label="Stored cases"
          tone="accent"
          value={
            casesResult.data ? formatNumber(recoveryCases.length) : "Unavailable"
          }
        />
        <MetricCard
          detail="Cases that still need operator action or outbound dispute work."
          label="Open cases"
          tone="warning"
          value={formatNumber(getCaseStatusCount(recoveryCases, "open"))}
        />
        <MetricCard
          detail="Cases waiting on review, carrier response, or follow-up."
          label="Pending cases"
          value={formatNumber(getCaseStatusCount(recoveryCases, "pending"))}
        />
        <MetricCard
          detail="Cases already closed out in the recovery workflow."
          label="Resolved cases"
          tone="good"
          value={formatNumber(getCaseStatusCount(recoveryCases, "resolved"))}
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          action={
            <span className="chip">
              {casesResult.error
                ? "Case register unavailable"
                : `${formatNumber(recoveryCases.length)} case${recoveryCases.length === 1 ? "" : "s"}`}
            </span>
          }
          className="span-7"
          description="Each case stays linked to one or more issues, along with the editable drafts and workflow status operators use to drive recovery."
          kicker="Register"
          title="Case queue"
        >
          {casesResult.error ? (
            <EmptyState
              description={casesResult.error}
              title="Cases could not be loaded."
              tone="danger"
            />
          ) : recoveryCases.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Status</th>
                    <th>Linked issues</th>
                    <th>Recoverable</th>
                    <th>Updated</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {recoveryCases.map((recoveryCase) => (
                    <tr key={recoveryCase.id}>
                      <td>
                        <Link className="table-link-button" href={`/cases/${recoveryCase.id}`}>
                          <span className="table-link-title">{recoveryCase.title}</span>
                          <span className="table-note mono">{recoveryCase.id}</span>
                        </Link>
                      </td>
                      <td>
                        <StatusBadge label={formatStatusLabel(recoveryCase.status)} />
                      </td>
                      <td>{formatNumber(recoveryCase.issue_count)}</td>
                      <td>{formatCurrency(recoveryCase.estimated_recoverable_amount)}</td>
                      <td>{formatDateTime(recoveryCase.updated_at)}</td>
                      <td className="is-action">
                        <Link className="table-action-button" href={`/cases/${recoveryCase.id}`}>
                          Open case
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              action={
                <Link className="button button-primary" href="/issues">
                  Review issue queue
                </Link>
              }
              description="No recovery cases have been created yet. Select one or more issues from the issue queue to open the first case."
              title="No cases stored yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-5"
          description="Issue pressure still matters even before a case exists. These provider clusters show where the best case-building candidates are accumulating."
          kicker="Candidates"
          title="Likely case drivers"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Candidate issue data is unavailable."
              tone="danger"
            />
          ) : dashboardResult.data?.issues_by_provider.length ? (
            <div className="stack-list">
              {dashboardResult.data.issues_by_provider.slice(0, 5).map((provider) => (
                <div className="list-row" key={provider.provider_name}>
                  <div className="list-row-main">
                    <p className="list-row-title">{provider.provider_name}</p>
                    <p className="list-row-detail">
                      {formatNumber(provider.count)} issues available to group into cases
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
              description="Issue candidates will appear as soon as the backend has modeled recovery findings."
              title="No case candidates yet"
            />
          )}
        </SectionCard>
      </section>
    </div>
  );
}
