import type { NumericValue } from "./api-types";

type DateTimeFormatOptions = {
  timeZone?: string;
};

type DateFormatOptions = Intl.DateTimeFormatOptions & {
  timeZone?: string;
};

export function parseNumericValue(value: NumericValue | null | undefined) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

export function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

export function formatCurrency(value: NumericValue | null | undefined) {
  const amount = parseNumericValue(value);

  if (amount === null) {
    return "Unavailable";
  }

  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(amount);
}

export function formatPercent(value: NumericValue | null | undefined) {
  const amount = parseNumericValue(value);

  if (amount === null) {
    return "Not scored";
  }

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    style: "percent",
  }).format(amount);
}

export function formatBytes(value: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let nextValue = value;
  let unitIndex = 0;

  while (nextValue >= 1024 && unitIndex < units.length - 1) {
    nextValue /= 1024;
    unitIndex += 1;
  }

  const digits = unitIndex === 0 ? 0 : 1;
  return `${nextValue.toFixed(digits)} ${units[unitIndex]}`;
}

function parseDateValue(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDate(
  value: string | null | undefined,
  options?: DateFormatOptions,
) {
  if (!value) {
    return "Not available";
  }

  const parsed = parseDateValue(value);

  if (parsed === null) {
    return value;
  }

  const { timeZone, ...intlOptions } = options ?? {};
  const resolvedOptions =
    Object.keys(intlOptions).length > 0
      ? intlOptions
      : { dateStyle: "medium" as const };

  return new Intl.DateTimeFormat("en-US", {
    ...resolvedOptions,
    ...(timeZone ? { timeZone } : {}),
  }).format(parsed);
}

export function formatDateTime(
  value: string | null | undefined,
  options?: DateTimeFormatOptions,
) {
  if (!value) {
    return "Not available";
  }

  const parsed = parseDateValue(value);

  if (parsed === null) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    ...(options?.timeZone ? { timeZone: options.timeZone } : {}),
  }).format(parsed);
}

export function formatStatusLabel(value: string | null | undefined) {
  if (!value) {
    return "Not set";
  }

  return value
    .split(/[_-]/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
