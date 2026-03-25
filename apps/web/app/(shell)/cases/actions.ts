"use server";

import { redirect } from "next/navigation";

import { createCase, updateCase } from "../../_lib/api";
import type { RecoveryCaseStatus } from "../../_lib/api-types";

function readStringValue(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value : "";
}

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

function readSafeReturnPath(value: FormDataEntryValue | null) {
  const normalizedValue = readStringValue(value).trim();

  if (!normalizedValue.startsWith("/issues")) {
    return "/issues";
  }

  return normalizedValue;
}

function readStatusValue(value: FormDataEntryValue | null): RecoveryCaseStatus {
  const normalizedValue = readStringValue(value).trim();

  if (
    normalizedValue === "open" ||
    normalizedValue === "pending" ||
    normalizedValue === "resolved"
  ) {
    return normalizedValue;
  }

  return "open";
}

export async function createRecoveryCaseAction(formData: FormData) {
  const issueIds = formData
    .getAll("issue_id")
    .map((value) => readStringValue(value).trim())
    .filter(Boolean);
  const returnPath = readSafeReturnPath(formData.get("return_to"));

  if (!issueIds.length) {
    redirect(
      buildRedirectUrl(returnPath, {
        case_error: "Select at least one issue before creating a case.",
      }),
    );
  }

  const result = await createCase({ issue_ids: issueIds });

  if (!result.data) {
    redirect(
      buildRedirectUrl(returnPath, {
        case_error: result.error ?? "Unable to create a recovery case.",
      }),
    );
  }

  redirect(
    buildRedirectUrl(`/cases/${result.data.id}`, {
      notice: "Recovery case created.",
    }),
  );
}

export async function updateRecoveryCaseAction(formData: FormData) {
  const caseId = readStringValue(formData.get("case_id")).trim();

  if (!caseId) {
    redirect(
      buildRedirectUrl("/cases", {
        error: "Recovery case ID is missing.",
      }),
    );
  }

  const result = await updateCase(caseId, {
    draft_email: readStringValue(formData.get("draft_email")).trim() || null,
    draft_summary: readStringValue(formData.get("draft_summary")).trim() || null,
    status: readStatusValue(formData.get("status")),
    title: readStringValue(formData.get("title")).trim(),
  });

  if (!result.data) {
    redirect(
      buildRedirectUrl(`/cases/${caseId}`, {
        error: result.error ?? "Unable to save the recovery case.",
      }),
    );
  }

  redirect(
    buildRedirectUrl(`/cases/${caseId}`, {
      notice: "Recovery case saved.",
    }),
  );
}
