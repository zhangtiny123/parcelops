import type { RecoveryIssue, RecoveryIssueFilters } from "../../_lib/api-types";

export type IssuePageSearchParams = Record<string, string | string[] | undefined>;

type IssueFilterKey = keyof RecoveryIssueFilters;

type IssueFilterOption = {
  label: string;
  value: string;
};

type IssueContextEntry = {
  label: string;
  value: string;
};

type IssueEvidenceEntry = IssueContextEntry & {
  key: string;
};

const ISSUE_FILTER_KEYS: IssueFilterKey[] = [
  "issue_type",
  "provider_name",
  "severity",
  "status",
  "shipment_id",
  "parcel_invoice_line_id",
  "three_pl_invoice_line_id",
];

const ISSUE_FILTER_LABELS: Record<IssueFilterKey, string> = {
  issue_type: "Issue type",
  parcel_invoice_line_id: "Parcel invoice line",
  provider_name: "Provider",
  severity: "Severity",
  shipment_id: "Shipment ID",
  status: "Status",
  three_pl_invoice_line_id: "3PL invoice line",
};

const CONTEXT_EVIDENCE_LABELS: Record<string, string> = {
  canonical_parcel_invoice_line_id: "Canonical parcel invoice line",
  charge_type: "Charge type",
  duplicate_count: "Duplicate count",
  duplicate_parcel_invoice_line_id: "Duplicate parcel invoice line",
  external_order_id: "External order ID",
  invoice_number: "Invoice number",
  order_id: "Order ID",
  order_number: "Order number",
  quantity: "Quantity",
  raw_row_ref: "Raw row reference",
  service_level_billed: "Billed service level",
  shipment_tracking_number: "Shipment tracking number",
  sku: "SKU",
  tracking_number: "Tracking number",
  warehouse_id: "Warehouse ID",
  zone_billed: "Billed zone",
};

const PREFERRED_CONTEXT_KEYS = [
  "invoice_number",
  "tracking_number",
  "shipment_tracking_number",
  "order_id",
  "order_number",
  "external_order_id",
  "warehouse_id",
  "charge_type",
  "service_level_billed",
  "zone_billed",
  "quantity",
  "sku",
  "duplicate_count",
  "canonical_parcel_invoice_line_id",
  "duplicate_parcel_invoice_line_id",
  "raw_row_ref",
] as const;

function getQueryValue(value: string | string[] | undefined) {
  const candidate = Array.isArray(value) ? value[0] : value;

  if (typeof candidate !== "string") {
    return undefined;
  }

  const normalized = candidate.trim();
  return normalized ? normalized : undefined;
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean))).sort(
    (left, right) => left.localeCompare(right),
  );
}

function toStringValue(value: unknown) {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "string") {
    const normalized = value.trim();
    return normalized ? normalized : null;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return null;
}

export function formatEvidenceLabel(key: string) {
  const explicitLabel = CONTEXT_EVIDENCE_LABELS[key];

  if (explicitLabel) {
    return explicitLabel;
  }

  return key
    .replace(/^three_pl/, "3pl")
    .split(/[_-]/)
    .filter(Boolean)
    .map((segment) => {
      const lower = segment.toLowerCase();

      if (lower === "3pl") {
        return "3PL";
      }

      if (lower === "id") {
        return "ID";
      }

      if (lower === "sku") {
        return "SKU";
      }

      if (lower === "lb") {
        return "lb";
      }

      return segment.charAt(0).toUpperCase() + segment.slice(1);
    })
    .join(" ");
}

export function formatEvidenceValue(value: unknown) {
  if (value === null || value === undefined) {
    return "Not available";
  }

  if (typeof value === "string") {
    return value.trim() || "Not available";
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value);
}

export function stringifyIssueEvidence(issue: RecoveryIssue) {
  return JSON.stringify(issue.evidence_json, null, 2);
}

export function readIssueFilters(
  searchParams?: IssuePageSearchParams,
): RecoveryIssueFilters {
  const filters: RecoveryIssueFilters = {};

  for (const key of ISSUE_FILTER_KEYS) {
    const value = getQueryValue(searchParams?.[key]);

    if (value) {
      filters[key] = value;
    }
  }

  return filters;
}

export function hasActiveIssueFilters(filters: RecoveryIssueFilters) {
  return ISSUE_FILTER_KEYS.some((key) => Boolean(filters[key]));
}

export function listActiveIssueFilters(filters: RecoveryIssueFilters) {
  return ISSUE_FILTER_KEYS.flatMap((key) => {
    const value = filters[key];

    if (!value) {
      return [];
    }

    return [{ label: ISSUE_FILTER_LABELS[key], value }];
  });
}

export function toIssueSearchParams(filters: RecoveryIssueFilters) {
  const searchParams = new URLSearchParams();

  for (const key of ISSUE_FILTER_KEYS) {
    const value = filters[key];

    if (value) {
      searchParams.set(key, value);
    }
  }

  return searchParams;
}

export function buildIssueFilterOptions(issues: RecoveryIssue[]) {
  const toOptions = (values: string[]): IssueFilterOption[] =>
    uniqueSorted(values).map((value) => ({
      label: value,
      value,
    }));

  return {
    issueTypes: toOptions(issues.map((issue) => issue.issue_type)),
    providers: toOptions(issues.map((issue) => issue.provider_name)),
    severities: toOptions(issues.map((issue) => issue.severity)),
    statuses: toOptions(issues.map((issue) => issue.status)),
  };
}

export function getIssueContextEntries(issue: RecoveryIssue): IssueContextEntry[] {
  const entries: IssueContextEntry[] = [];
  const seenValues = new Set<string>();

  const pushEntry = (label: string, value: unknown) => {
    const normalizedValue = toStringValue(value);

    if (normalizedValue === null || seenValues.has(`${label}:${normalizedValue}`)) {
      return;
    }

    entries.push({ label, value: normalizedValue });
    seenValues.add(`${label}:${normalizedValue}`);
  };

  pushEntry("Shipment ID", issue.shipment_id);
  pushEntry("Parcel invoice line", issue.parcel_invoice_line_id);
  pushEntry("3PL invoice line", issue.three_pl_invoice_line_id);

  for (const key of PREFERRED_CONTEXT_KEYS) {
    pushEntry(formatEvidenceLabel(key), issue.evidence_json[key]);
  }

  return entries;
}

export function getReadableEvidenceEntries(
  issue: RecoveryIssue,
): IssueEvidenceEntry[] {
  return Object.entries(issue.evidence_json)
    .map(([key, value]) => ({
      key,
      label: formatEvidenceLabel(key),
      value: formatEvidenceValue(value),
    }))
    .sort((left, right) => {
      const leftIndex = PREFERRED_CONTEXT_KEYS.indexOf(
        left.key as (typeof PREFERRED_CONTEXT_KEYS)[number],
      );
      const rightIndex = PREFERRED_CONTEXT_KEYS.indexOf(
        right.key as (typeof PREFERRED_CONTEXT_KEYS)[number],
      );

      const normalizedLeftIndex = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
      const normalizedRightIndex =
        rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;

      if (normalizedLeftIndex !== normalizedRightIndex) {
        return normalizedLeftIndex - normalizedRightIndex;
      }

      return left.label.localeCompare(right.label);
    });
}
