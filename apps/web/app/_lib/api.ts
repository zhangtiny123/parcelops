import "server-only";

export type {
  ApiHealth,
  ApiMeta,
  ApiResult,
  CanonicalField,
  ColumnMapping,
  ColumnMappingSuggestion,
  NumericValue,
  RecoveryIssue,
  RecoveryIssueDashboard,
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
  RecoveryIssue,
  RecoveryIssueDashboard,
  UploadJob,
} from "./api-types";

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
