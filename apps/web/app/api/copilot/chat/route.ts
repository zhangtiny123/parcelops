import { makeServerApiUrl } from "../../../_lib/api";

export const dynamic = "force-dynamic";

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

export async function POST(request: Request) {
  try {
    const response = await fetch(makeServerApiUrl("/copilot/chat"), {
      body: (await request.text()) || undefined,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      method: "POST",
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
