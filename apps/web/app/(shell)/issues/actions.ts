"use server";

import { redirect } from "next/navigation";

import { triggerIssueDetection } from "../../_lib/api";

function buildRedirectUrl(
  path: string,
  params: Record<string, string | null | undefined>,
) {
  const url = new URL(path, "http://parcelops.local");

  for (const [key, value] of Object.entries(params)) {
    const normalizedValue = value?.trim();

    if (!normalizedValue) {
      continue;
    }

    url.searchParams.set(key, normalizedValue);
  }

  return `${url.pathname}${url.search}`;
}

export async function triggerIssueDetectionAction() {
  const result = await triggerIssueDetection();

  if (!result.data) {
    redirect(
      buildRedirectUrl("/issues", {
        error: result.error ?? "Unable to run issue detection.",
      }),
    );
  }

  redirect(
    buildRedirectUrl("/issues", {
      notice: `Issue detection completed. ${result.data.created_count} created, ${result.data.updated_count} updated, ${result.data.unchanged_count} unchanged.`,
    }),
  );
}
