import "server-only";

export type NumericValue = number | string;

export type ApiResult<T> =
  | { data: T; error: null; status: number }
  | { data: null; error: string; status: number | null };

export type ApiMeta = {
  db_health_url: string;
  docs_url: string;
  health_url: string;
  issues_url: string;
  name: string;
  service: string;
  uploads_url: string;
};

export type ApiHealth = {
  dependencies: {
    postgres_db: string;
    postgres_host: string;
    redis_host: string;
  };
  environment: string;
  max_upload_size_bytes: number;
  service: string;
  status: string;
  storage_root: string;
};

export type UploadJob = {
  file_size_bytes: number;
  file_type: string;
  id: string;
  last_error: string | null;
  normalization_completed_at: string | null;
  normalization_error_count: number;
  normalization_started_at: string | null;
  normalization_task_id: string | null;
  normalized_row_count: number;
  original_filename: string;
  source_kind: string | null;
  status: string;
  uploaded_at: string;
};

export type RecoveryIssue = {
  confidence: NumericValue | null;
  detected_at: string;
  estimated_recoverable_amount: NumericValue | null;
  evidence_json: Record<string, unknown>;
  id: string;
  issue_type: string;
  parcel_invoice_line_id: string | null;
  provider_name: string;
  severity: string;
  shipment_id: string | null;
  status: string;
  summary: string;
  three_pl_invoice_line_id: string | null;
};

export type RecoveryIssueTypeMetric = {
  count: number;
  estimated_recoverable_amount: NumericValue;
  issue_type: string;
};

export type RecoveryIssueProviderMetric = {
  count: number;
  estimated_recoverable_amount: NumericValue;
  provider_name: string;
};

export type RecoveryIssueTrendPoint = {
  count: number;
  date: string;
  estimated_recoverable_amount: NumericValue;
};

export type RecoveryIssueDashboard = {
  issues_by_provider: RecoveryIssueProviderMetric[];
  issues_by_type: RecoveryIssueTypeMetric[];
  total_issue_count: number;
  total_recoverable_amount: NumericValue;
  trend: RecoveryIssueTrendPoint[];
};

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function extractErrorMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;

    if (typeof detail === "string") {
      return detail;
    }
  }

  return fallback;
}

export function getApiBaseUrl() {
  return trimTrailingSlash(
    process.env.API_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      DEFAULT_API_BASE_URL,
  );
}

export function makeApiUrl(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalizedPath}`;
}

async function requestJson<T>(path: string): Promise<ApiResult<T>> {
  try {
    const response = await fetch(makeApiUrl(path), {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      let errorPayload: unknown = null;

      try {
        errorPayload = await response.json();
      } catch {
        errorPayload = null;
      }

      return {
        data: null,
        error: extractErrorMessage(
          errorPayload,
          `Request failed with status ${response.status}.`,
        ),
        status: response.status,
      };
    }

    return {
      data: (await response.json()) as T,
      error: null,
      status: response.status,
    };
  } catch (error) {
    return {
      data: null,
      error:
        error instanceof Error ? error.message : "Unable to reach the backend API.",
      status: null,
    };
  }
}

export function getApiMeta() {
  return requestJson<ApiMeta>("/");
}

export function getApiHealth() {
  return requestJson<ApiHealth>("/health");
}

export function getIssueDashboard(days = 30) {
  return requestJson<RecoveryIssueDashboard>(`/issues/dashboard?days=${days}`);
}

export function listHighSeverityIssues(limit = 5) {
  return requestJson<RecoveryIssue[]>(`/issues/high-severity?limit=${limit}`);
}

export function listIssues() {
  return requestJson<RecoveryIssue[]>("/issues");
}

export function listUploads() {
  return requestJson<UploadJob[]>("/uploads");
}
