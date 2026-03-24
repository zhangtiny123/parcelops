import Link from "next/link";

import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard } from "../../_components/ui";
import { getIssueDashboard } from "../../_lib/api";
import { formatCurrency, formatNumber } from "../../_lib/format";

export default async function CasesPage() {
  const dashboardResult = await getIssueDashboard();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Cases"
        title="Recovery case register"
        description="Case storage and editing are still ahead, but the shell is ready to turn issue findings into a durable operations workflow."
      >
        <div className="page-action-row">
          <Link className="button button-secondary" href="/issues">
            Review issue queue
          </Link>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Case readiness">
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : "Potential issue inputs that can later be grouped into cases."
          }
          label="Eligible issues"
          tone="accent"
          value={
            dashboardResult.data
              ? formatNumber(dashboardResult.data.total_issue_count)
              : "Unavailable"
          }
        />
        <MetricCard
          detail="Estimated recoverable value the future case workflow can package."
          tone="good"
          label="Recoverable value"
          value={
            dashboardResult.data
              ? formatCurrency(dashboardResult.data.total_recoverable_amount)
              : "Unavailable"
          }
        />
        <MetricCard
          detail="The backend case model and APIs land in Task 12."
          label="Stored cases"
          value="Pending"
        />
        <MetricCard
          detail="Navigation is already in place so operators have a stable destination."
          label="Workflow stage"
          value="Shell ready"
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-7"
          description="What will become the durable recovery case register."
          kicker="Register"
          title="Case list placeholder"
        >
          <EmptyState
            description="Task 12 will add case creation, open/pending/resolved status management, and editable dispute drafts on this route."
            title="Cases are not stored yet"
          />
        </SectionCard>

        <SectionCard
          className="span-5"
          description="Current issue pressure that will likely seed early case creation."
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
                      {formatNumber(provider.count)} issues that could be batched
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
              description="Once issue detection produces findings, this panel will highlight the best case-building candidates."
              title="No case candidates yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-12"
          description="The future case workflow will sit directly on top of the issue model already present."
          kicker="Preview"
          title="Planned case structure"
        >
          <ul className="bullet-list">
            <li>Bundle one or more issues into an operator-owned recovery case.</li>
            <li>Persist open, pending, and resolved status transitions.</li>
            <li>Draft and edit summary and email content without losing evidence linkage.</li>
            <li>Keep cases grounded in the same issue types and providers visible today.</li>
          </ul>
        </SectionCard>
      </section>
    </div>
  );
}
