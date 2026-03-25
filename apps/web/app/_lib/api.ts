import "server-only";

export type {
  ApiHealth,
  ApiMeta,
  ApiResult,
  CanonicalField,
  ColumnMapping,
  ColumnMappingSuggestion,
  NumericValue,
  RecoveryCase,
  RecoveryCaseCreateRequest,
  RecoveryCaseLinkedIssue,
  RecoveryCaseListItem,
  RecoveryCaseStatus,
  RecoveryCaseUpdateRequest,
  RecoveryIssueDetection,
  RecoveryIssue,
  RecoveryIssueDashboard,
  RecoveryIssueFilters,
  RecoveryIssueProviderMetric,
  RecoveryIssueTrendPoint,
  RecoveryIssueTypeMetric,
  UploadJob,
  UploadMapping,
  UploadMappingWrite,
  UploadPreview,
  UploadSuggestedMapping,
} from "./api-types";

import type {
  ApiHealth,
  ApiMeta,
  ApiResult,
  RecoveryCase,
  RecoveryCaseCreateRequest,
  RecoveryCaseListItem,
  RecoveryCaseUpdateRequest,
  RecoveryIssueDetection,
  RecoveryIssue,
  RecoveryIssueDashboard,
  RecoveryIssueFilters,
  UploadJob,
} from "./api-types";

const DEFAULT_PUBLIC_API_BASE_URL = "http://localhost:8000";
const DEFAULT_SERVER_API_BASE_URL = "http://localhost:8000";

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

export function getPublicApiBaseUrl() {
  return trimTrailingSlash(
    process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_PUBLIC_API_BASE_URL,
  );
}

export function getServerApiBaseUrl() {
  return trimTrailingSlash(
    process.env.API_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      DEFAULT_SERVER_API_BASE_URL,
  );
}

export function makeApiUrl(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getPublicApiBaseUrl()}${normalizedPath}`;
}

export function makeServerApiUrl(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getServerApiBaseUrl()}${normalizedPath}`;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const headers = new Headers({
      Accept: "application/json",
    });

    if (init?.headers) {
      const initHeaders = new Headers(init.headers);
      initHeaders.forEach((value, key) => {
        headers.set(key, value);
      });
    }

    const response = await fetch(makeServerApiUrl(path), {
      cache: "no-store",
      ...init,
      headers,
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

function buildQueryString(
  params: Record<string, number | string | undefined>,
) {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    const normalizedValue =
      typeof value === "string" ? value.trim() : value;

    if (
      normalizedValue === undefined ||
      normalizedValue === "" ||
      normalizedValue === null
    ) {
      continue;
    }

    searchParams.set(key, String(normalizedValue));
  }

  return searchParams.size ? `?${searchParams.toString()}` : "";
}

export function getApiMeta() {
  return requestJson<ApiMeta>("/");
}

export function getApiHealth() {
  return requestJson<ApiHealth>("/health");
}

export function listCases() {
  return requestJson<RecoveryCaseListItem[]>("/cases");
}

export function getCase(caseId: string) {
  return requestJson<RecoveryCase>(`/cases/${caseId}`);
}

export function getIssueDashboard(days = 30) {
  return requestJson<RecoveryIssueDashboard>(`/issues/dashboard?days=${days}`);
}

export function triggerIssueDetection() {
  return requestJson<RecoveryIssueDetection>("/issues/detect", {
    method: "POST",
  });
}

export function listHighSeverityIssues(limit = 5) {
  return requestJson<RecoveryIssue[]>(`/issues/high-severity?limit=${limit}`);
}

export function getIssue(issueId: string) {
  return requestJson<RecoveryIssue>(`/issues/${issueId}`);
}

export function listIssues(filters: RecoveryIssueFilters = {}) {
  return requestJson<RecoveryIssue[]>(`/issues${buildQueryString(filters)}`);
}

export function listUploads() {
  return requestJson<UploadJob[]>("/uploads");
}

export function createCase(payload: RecoveryCaseCreateRequest) {
  return requestJson<RecoveryCase>("/cases", {
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
  });
}

export function updateCase(caseId: string, payload: RecoveryCaseUpdateRequest) {
  return requestJson<RecoveryCase>(`/cases/${caseId}`, {
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
    },
    method: "PUT",
  });
}
