import type {
  ApiResult,
  UploadJob,
  UploadMapping,
  UploadMappingWrite,
  UploadPreview,
  UploadSuggestedMapping,
} from "./api-types";

function extractErrorMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;

    if (typeof detail === "string") {
      return detail;
    }
  }

  return fallback;
}

async function requestUploadApi<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(path, {
      ...init,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
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
        error instanceof Error ? error.message : "Unable to reach the web upload API.",
      status: null,
    };
  }
}

export function listBrowserUploads() {
  return requestUploadApi<UploadJob[]>("/api/uploads");
}

export function getBrowserUpload(uploadId: string) {
  return requestUploadApi<UploadJob>(`/api/uploads/${uploadId}`);
}

export function getBrowserUploadPreview(uploadId: string) {
  return requestUploadApi<UploadPreview>(`/api/uploads/${uploadId}/preview`);
}

export function getBrowserSuggestedMapping(
  uploadId: string,
  sourceKind?: string,
) {
  const searchParams = new URLSearchParams();

  if (sourceKind) {
    searchParams.set("source_kind", sourceKind);
  }

  const suffix = searchParams.size ? `?${searchParams.toString()}` : "";
  return requestUploadApi<UploadSuggestedMapping>(
    `/api/uploads/${uploadId}/suggested-mapping${suffix}`,
  );
}

export function saveBrowserUploadMapping(
  uploadId: string,
  payload: UploadMappingWrite,
) {
  return requestUploadApi<UploadMapping>(`/api/uploads/${uploadId}/mapping`, {
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
    },
    method: "PUT",
  });
}

export function triggerBrowserUploadNormalization(uploadId: string) {
  return requestUploadApi<UploadJob>(`/api/uploads/${uploadId}/normalize`, {
    method: "POST",
  });
}

export function uploadBrowserFile(file: File) {
  const formData = new FormData();
  formData.append("file", file, file.name);

  return requestUploadApi<UploadJob>("/api/uploads", {
    body: formData,
    method: "POST",
  });
}
