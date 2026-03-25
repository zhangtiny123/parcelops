import Link from "next/link";

import { PageHeader } from "../../_components/page-header";
import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import { getIssueDashboard, listIssues, makeApiUrl } from "../../_lib/api";
import type { NumericValue, RecoveryIssueFilters } from "../../_lib/api-types";
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatStatusLabel,
  parseNumericValue,
} from "../../_lib/format";
import {
  buildIssueFilterOptions,
  hasActiveIssueFilters,
  listActiveIssueFilters,
  readIssueFilters,
  toIssueSearchParams,
  type IssuePageSearchParams,
} from "./issue-utils";

const DASHBOARD_WINDOW_DAYS = 30;
const TREND_POINT_LIMIT = 14;

type IssuesPageProps = {
  searchParams?: IssuePageSearchParams;
};

type RankedMetric = {
  amount: NumericValue;
  count: number;
  key: string;
  label: string;
};

function buildIssueDetailHref(
  issueId: string,
  filters: RecoveryIssueFilters,
) {
  const search = toIssueSearchParams(filters).toString();
  return search ? `/issues/${issueId}?${search}` : `/issues/${issueId}`;
}

function formatActiveFilterValue(label: string, value: string) {
  if (label === "Issue type" || label === "Severity" || label === "Status") {
    return formatStatusLabel(value);
  }

  return value;
}

function getMaxMetricCount(metrics: RankedMetric[]) {
  return Math.max(...metrics.map((metric) => metric.count), 1);
}

function getTrendBarHeight(value: number, maxValue: number) {
  if (value <= 0 || maxValue <= 0) {
    return "8%";
  }

  return `${Math.max((value / maxValue) * 100, 18)}%`;
}

function RankedMetricList({ metrics }: { metrics: RankedMetric[] }) {
  const maxCount = getMaxMetricCount(metrics);

  return (
    <div className="ranked-list">
      {metrics.map((metric) => (
        <div className="ranked-row" key={metric.key}>
          <div className="ranked-row-copy">
            <div className="ranked-row-header">
              <p className="ranked-row-title">{metric.label}</p>
              <p className="ranked-row-value">{formatNumber(metric.count)} issues</p>
            </div>
            <div className="ranked-row-bar" aria-hidden="true">
              <span
                className="ranked-row-fill"
                style={{ width: `${Math.max((metric.count / maxCount) * 100, 12)}%` }}
              />
            </div>
            <p className="ranked-row-detail">
              {formatCurrency(metric.amount)} estimated recoverable amount
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default async function IssuesPage({ searchParams }: IssuesPageProps) {
  const filters = readIssueFilters(searchParams);
  const hasActiveFilters = hasActiveIssueFilters(filters);

  const [dashboardResult, catalogIssuesResult, filteredIssuesResult] = await Promise.all([
    getIssueDashboard(DASHBOARD_WINDOW_DAYS),
    listIssues(),
    hasActiveFilters ? listIssues(filters) : Promise.resolve(null),
  ]);

  const catalogIssues = catalogIssuesResult.data ?? [];
  const issues = hasActiveFilters
    ? filteredIssuesResult?.data ?? []
    : catalogIssues;
  const activeFilters = listActiveIssueFilters(filters);
  const filterOptions = buildIssueFilterOptions(
    catalogIssues.length ? catalogIssues : issues,
  );
  const issuesError = hasActiveFilters
    ? filteredIssuesResult?.error ?? null
    : catalogIssuesResult.error;
  const filterSearch = toIssueSearchParams(filters).toString();
  const issuesApiHref = makeApiUrl(filterSearch ? `/issues?${filterSearch}` : "/issues");

  const dashboard = dashboardResult.data;
  const topProvider = dashboard?.issues_by_provider[0] ?? null;
  const topIssueType = dashboard?.issues_by_type[0] ?? null;
  const trendPoints = dashboard?.trend.slice(-TREND_POINT_LIMIT) ?? [];
  const maxTrendCount = Math.max(...trendPoints.map((point) => point.count), 1);
  const peakTrendPoint =
    trendPoints.reduce<typeof trendPoints[number] | null>((currentPeak, point) => {
      if (currentPeak === null || point.count > currentPeak.count) {
        return point;
      }

      return currentPeak;
    }, null) ?? null;
  const filteredRecoverableAmount = issues.reduce((total, issue) => {
    return total + (parseNumericValue(issue.estimated_recoverable_amount) ?? 0);
  }, 0);
  const hasFilterMetadataFallback =
    Boolean(catalogIssuesResult.error) && issues.length > 0 && catalogIssues.length === 0;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Issues"
        title="Recovery issue dashboard"
        description="Monitor recoverable exposure, narrow the queue with server-backed filters, and open each issue with enough context to decide the next recovery action."
      >
        <div className="page-action-row">
          {hasActiveFilters ? (
            <Link className="button button-secondary" href="/issues">
              Clear filters
            </Link>
          ) : null}
          <a
            className="button button-primary"
            href={issuesApiHref}
            rel="noreferrer"
            target="_blank"
          >
            Issues API
          </a>
        </div>
      </PageHeader>

      <section className="metric-grid" aria-label="Issue dashboard metrics">
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : `Modeled recoverable value in the last ${DASHBOARD_WINDOW_DAYS} days.`
          }
          label="Recoverable amount"
          tone="accent"
          value={
            dashboard ? formatCurrency(dashboard.total_recoverable_amount) : "Unavailable"
          }
        />
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : `${formatNumber(dashboard?.issues_by_type.length ?? 0)} issue types and ${formatNumber(
                  dashboard?.issues_by_provider.length ?? 0,
                )} providers are contributing to the queue.`
          }
          label="Issues modeled"
          tone="good"
          value={dashboard ? formatNumber(dashboard.total_issue_count) : "Unavailable"}
        />
        <MetricCard
          detail={
            issuesError
              ? issuesError
              : hasActiveFilters
                ? `${formatCurrency(filteredRecoverableAmount)} across the filtered issue set.`
                : "Showing the full current issue register."
          }
          label={hasActiveFilters ? "Filtered results" : "Current queue"}
          tone="warning"
          value={issuesError ? "Unavailable" : formatNumber(issues.length)}
        />
        <MetricCard
          detail={
            dashboardResult.error
              ? dashboardResult.error
              : topProvider
                ? `${formatNumber(topProvider.count)} issues totaling ${formatCurrency(
                    topProvider.estimated_recoverable_amount,
                  )}.`
                : "No provider concentration has been modeled yet."
          }
          label="Leading provider"
          value={topProvider?.provider_name ?? "Not available"}
        />
      </section>

      <section className="content-grid content-grid--two">
        <SectionCard
          className="span-7"
          description="Recent issue volume over the trailing summary window. Bars show issue counts; the callouts highlight the latest recoverable dollar movement."
          kicker="Trend"
          title="Recent issue pressure"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Trend data is unavailable."
              tone="danger"
            />
          ) : trendPoints.length ? (
            <div className="trend-layout">
              <div className="trend-chart" aria-label="Recent issue trend">
                {trendPoints.map((point) => (
                  <div className="trend-column" key={point.date}>
                    <p className="trend-column-value">{formatNumber(point.count)}</p>
                    <div className="trend-column-track" aria-hidden="true">
                      <span
                        className="trend-column-fill"
                        style={{ height: getTrendBarHeight(point.count, maxTrendCount) }}
                      />
                    </div>
                    <p className="trend-column-label">
                      {formatDate(point.date, { day: "numeric", month: "short" })}
                    </p>
                  </div>
                ))}
              </div>

              <div className="detail-grid">
                <div className="detail-item">
                  <p className="status-label">Peak day</p>
                  <p className="detail-value">
                    {peakTrendPoint
                      ? `${formatDate(peakTrendPoint.date)} · ${formatNumber(
                          peakTrendPoint.count,
                        )} issues`
                      : "No issue activity"}
                  </p>
                </div>
                <div className="detail-item">
                  <p className="status-label">Latest day</p>
                  <p className="detail-value">
                    {trendPoints.length
                      ? `${formatDate(trendPoints[trendPoints.length - 1].date)} · ${formatCurrency(
                          trendPoints[trendPoints.length - 1].estimated_recoverable_amount,
                        )}`
                      : "No trend points"}
                  </p>
                </div>
                <div className="detail-item">
                  <p className="status-label">Leading issue type</p>
                  <p className="detail-value">
                    {topIssueType
                      ? `${formatStatusLabel(topIssueType.issue_type)} (${formatNumber(
                          topIssueType.count,
                        )})`
                      : "No type distribution yet"}
                  </p>
                </div>
                <div className="detail-item">
                  <p className="status-label">Window recoverable</p>
                  <p className="detail-value">
                    {dashboard ? formatCurrency(dashboard.total_recoverable_amount) : "Unavailable"}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState
              description="Trend points will appear as soon as issue detection records daily activity."
              title="No trend data yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-5"
          description="Filters map directly to the backend issue list endpoint, so every refinement stays grounded in live issue records."
          kicker="Filters"
          title="Narrow the register"
        >
          <form action="/issues" className="filter-panel" method="get">
            <div className="filter-grid">
              <label className="field-group">
                <span className="field-label">Issue type</span>
                <select
                  className="field-select"
                  defaultValue={filters.issue_type ?? ""}
                  name="issue_type"
                >
                  <option value="">All issue types</option>
                  {filterOptions.issueTypes.map((option) => (
                    <option key={option.value} value={option.value}>
                      {formatStatusLabel(option.label)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-group">
                <span className="field-label">Provider</span>
                <select
                  className="field-select"
                  defaultValue={filters.provider_name ?? ""}
                  name="provider_name"
                >
                  <option value="">All providers</option>
                  {filterOptions.providers.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-group">
                <span className="field-label">Severity</span>
                <select
                  className="field-select"
                  defaultValue={filters.severity ?? ""}
                  name="severity"
                >
                  <option value="">All severities</option>
                  {filterOptions.severities.map((option) => (
                    <option key={option.value} value={option.value}>
                      {formatStatusLabel(option.label)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-group">
                <span className="field-label">Status</span>
                <select
                  className="field-select"
                  defaultValue={filters.status ?? ""}
                  name="status"
                >
                  <option value="">All statuses</option>
                  {filterOptions.statuses.map((option) => (
                    <option key={option.value} value={option.value}>
                      {formatStatusLabel(option.label)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field-group">
                <span className="field-label">Shipment ID</span>
                <input
                  className="field-input"
                  defaultValue={filters.shipment_id ?? ""}
                  name="shipment_id"
                  placeholder="ship-123"
                  type="text"
                />
              </label>

              <label className="field-group">
                <span className="field-label">Parcel invoice line</span>
                <input
                  className="field-input"
                  defaultValue={filters.parcel_invoice_line_id ?? ""}
                  name="parcel_invoice_line_id"
                  placeholder="parcel-line-456"
                  type="text"
                />
              </label>

              <label className="field-group">
                <span className="field-label">3PL invoice line</span>
                <input
                  className="field-input"
                  defaultValue={filters.three_pl_invoice_line_id ?? ""}
                  name="three_pl_invoice_line_id"
                  placeholder="tpl-line-789"
                  type="text"
                />
              </label>
            </div>

            <div className="filter-actions">
              <button className="button button-primary" type="submit">
                Apply filters
              </button>
              <Link className="button button-secondary" href="/issues">
                Reset
              </Link>
            </div>
          </form>

          {activeFilters.length ? (
            <div className="filter-chip-row" aria-label="Active filters">
              {activeFilters.map((filter) => (
                <span className="chip" key={`${filter.label}:${filter.value}`}>
                  {filter.label}: {formatActiveFilterValue(filter.label, filter.value)}
                </span>
              ))}
            </div>
          ) : null}

          {hasFilterMetadataFallback ? (
            <p className="workflow-note">
              Filter dropdown values are limited to the current results because the
              full issue catalog could not be loaded.
            </p>
          ) : null}
        </SectionCard>

        <SectionCard
          className="span-6"
          description="Issue-type concentration shows which anomaly classes are creating the most recoverable pressure."
          kicker="Mix"
          title="Counts by issue type"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Issue-type rollups are unavailable."
              tone="danger"
            />
          ) : dashboard?.issues_by_type.length ? (
            <RankedMetricList
              metrics={dashboard.issues_by_type.map((metric) => ({
                amount: metric.estimated_recoverable_amount,
                count: metric.count,
                key: metric.issue_type,
                label: formatStatusLabel(metric.issue_type),
              }))}
            />
          ) : (
            <EmptyState
              description="Run issue detection to populate issue-type rollups."
              title="No issue-type metrics yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-6"
          description="Provider concentration helps operators see where to focus recovery work first."
          kicker="Providers"
          title="Counts by provider"
        >
          {dashboardResult.error ? (
            <EmptyState
              description={dashboardResult.error}
              title="Provider rollups are unavailable."
              tone="danger"
            />
          ) : dashboard?.issues_by_provider.length ? (
            <RankedMetricList
              metrics={dashboard.issues_by_provider.map((metric) => ({
                amount: metric.estimated_recoverable_amount,
                count: metric.count,
                key: metric.provider_name,
                label: metric.provider_name,
              }))}
            />
          ) : (
            <EmptyState
              description="Provider clusters will appear as soon as issues are modeled."
              title="No provider metrics yet"
            />
          )}
        </SectionCard>

        <SectionCard
          action={
            <span className="chip">
              {issuesError
                ? "Issue list unavailable"
                : `${formatNumber(issues.length)} visible issue${issues.length === 1 ? "" : "s"}`}
            </span>
          }
          className="span-12"
          description="Every row stays linked to a detail page with recovery context and the underlying evidence payload."
          kicker="Register"
          title="Issue queue"
        >
          {issuesError ? (
            <EmptyState
              description={issuesError}
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
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Recoverable</th>
                    <th>Detected</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((issue) => (
                    <tr key={issue.id}>
                      <td>
                        <Link
                          className="table-link-button"
                          href={buildIssueDetailHref(issue.id, filters)}
                        >
                          <span className="table-link-title">
                            {formatStatusLabel(issue.issue_type)}
                          </span>
                          <span className="table-note">{issue.summary}</span>
                        </Link>
                      </td>
                      <td>{issue.provider_name}</td>
                      <td>
                        <StatusBadge label={formatStatusLabel(issue.severity)} />
                      </td>
                      <td>
                        <StatusBadge label={formatStatusLabel(issue.status)} />
                      </td>
                      <td>{formatPercent(issue.confidence)}</td>
                      <td>{formatCurrency(issue.estimated_recoverable_amount)}</td>
                      <td>{formatDateTime(issue.detected_at)}</td>
                      <td className="is-action">
                        <Link
                          className="table-action-button"
                          href={buildIssueDetailHref(issue.id, filters)}
                        >
                          View detail
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
                hasActiveFilters ? (
                  <Link className="button button-secondary" href="/issues">
                    Clear filters
                  </Link>
                ) : undefined
              }
              description={
                hasActiveFilters
                  ? "No issues match the current filters. Reset them to return to the full register."
                  : "This register will populate as soon as the backend has modeled recovery issues."
              }
              title={
                hasActiveFilters ? "No issues match these filters" : "No issues detected yet"
              }
            />
          )}
        </SectionCard>
      </section>
    </div>
  );
}
