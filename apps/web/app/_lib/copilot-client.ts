import type {
  ApiResult,
  CopilotChatRequest,
  CopilotChatResponse,
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

async function requestCopilotApi<T>(
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
        error instanceof Error ? error.message : "Unable to reach the copilot API.",
      status: null,
    };
  }
}

export function chatWithBrowserCopilot(payload: CopilotChatRequest) {
  return requestCopilotApi<CopilotChatResponse>("/api/copilot/chat", {
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
  });
}
