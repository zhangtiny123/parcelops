import { makeApiUrl } from "../../../_lib/api";

type RouteContext = {
  params: {
    path?: string[];
  };
};

export const dynamic = "force-dynamic";

function buildUpstreamPath(pathSegments: string[] | undefined) {
  if (!pathSegments?.length) {
    return "/uploads";
  }

  return `/uploads/${pathSegments.map(encodeURIComponent).join("/")}`;
}

function buildUpstreamUrl(request: Request, pathSegments: string[] | undefined) {
  const upstreamUrl = new URL(makeApiUrl(buildUpstreamPath(pathSegments)));
  const incomingUrl = new URL(request.url);
  upstreamUrl.search = incomingUrl.search;
  return upstreamUrl;
}

function buildProxyResponse(response: Response) {
  const headers = new Headers();
  const contentType = response.headers.get("content-type");

  if (contentType) {
    headers.set("content-type", contentType);
  }

  return new Response(response.body, {
    headers,
    status: response.status,
  });
}

async function proxyUploadRequest(
  request: Request,
  pathSegments: string[] | undefined,
  method: "GET" | "POST" | "PUT",
) {
  const headers = new Headers({
    Accept: "application/json",
  });

  let body: BodyInit | undefined;

  if (method !== "GET") {
    const contentType = request.headers.get("content-type") ?? "";

    if (contentType.includes("multipart/form-data")) {
      body = await request.formData();
    } else if (contentType.includes("application/json")) {
      body = await request.text();
      headers.set("content-type", "application/json");
    } else {
      const rawBody = await request.text();

      if (rawBody) {
        body = rawBody;
      }

      if (contentType) {
        headers.set("content-type", contentType);
      }
    }
  }

  try {
    const response = await fetch(buildUpstreamUrl(request, pathSegments), {
      body,
      cache: "no-store",
      headers,
      method,
    });

    return buildProxyResponse(response);
  } catch (error) {
    return Response.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : "Unable to reach the backend API.",
      },
      { status: 502 },
    );
  }
}

export function GET(request: Request, context: RouteContext) {
  return proxyUploadRequest(request, context.params.path, "GET");
}

export function POST(request: Request, context: RouteContext) {
  return proxyUploadRequest(request, context.params.path, "POST");
}

export function PUT(request: Request, context: RouteContext) {
  return proxyUploadRequest(request, context.params.path, "PUT");
}
