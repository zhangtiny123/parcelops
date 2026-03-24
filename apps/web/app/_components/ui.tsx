import type { ReactNode } from "react";

type MetricCardTone = "accent" | "good" | "warning";
type StatusBadgeTone = "danger" | "default" | "good" | "muted" | "warning";

type MetricCardProps = {
  detail: string;
  label: string;
  tone?: MetricCardTone;
  value: string;
};

type SectionCardProps = {
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  description: string;
  kicker?: string;
  title: string;
};

type EmptyStateProps = {
  action?: ReactNode;
  description: string;
  title: string;
  tone?: "danger";
};

type StatusBadgeProps = {
  label: string;
  tone?: StatusBadgeTone;
};

function joinClassNames(...classNames: Array<string | undefined>) {
  return classNames.filter(Boolean).join(" ");
}

function inferStatusTone(label: string): StatusBadgeTone {
  const value = label.toLowerCase();

  if (
    value.includes("ok") ||
    value.includes("connected") ||
    value.includes("ready") ||
    value.includes("normalized") ||
    value.includes("mapped")
  ) {
    return "good";
  }

  if (
    value.includes("offline") ||
    value.includes("failed") ||
    value.includes("error") ||
    value.includes("unavailable")
  ) {
    return "danger";
  }

  if (
    value.includes("queued") ||
    value.includes("normalizing") ||
    value.includes("pending")
  ) {
    return "warning";
  }

  if (value.includes("planned")) {
    return "muted";
  }

  return "default";
}

export function MetricCard({ detail, label, tone, value }: MetricCardProps) {
  return (
    <article className={joinClassNames("metric-card", tone && `metric-card--${tone}`)}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      <p className="metric-detail">{detail}</p>
    </article>
  );
}

export function SectionCard({
  action,
  children,
  className,
  description,
  kicker,
  title,
}: SectionCardProps) {
  return (
    <article className={joinClassNames("section-card", className)}>
      <div className="section-header">
        <div>
          {kicker ? <p className="section-kicker">{kicker}</p> : null}
          <h2 className="section-title">{title}</h2>
          <p className="section-description">{description}</p>
        </div>
        {action ? action : null}
      </div>
      <div className="section-body">{children}</div>
    </article>
  );
}

export function EmptyState({
  action,
  description,
  title,
  tone,
}: EmptyStateProps) {
  return (
    <div className={joinClassNames("empty-state", tone && "empty-state--danger")}>
      <h3 className="empty-title">{title}</h3>
      <p className="empty-description">{description}</p>
      {action ? <div className="button-row">{action}</div> : null}
    </div>
  );
}

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  const resolvedTone = tone ?? inferStatusTone(label);

  return (
    <span className={`status-badge status-badge--${resolvedTone}`}>{label}</span>
  );
}
