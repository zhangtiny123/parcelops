import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({
    service: "web",
    status: "ok",
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  });
}
