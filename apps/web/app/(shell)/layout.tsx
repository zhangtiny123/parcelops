import type { ReactNode } from "react";

import { AppShell } from "../_components/app-shell";
import { getApiBaseUrl } from "../_lib/api";

export const dynamic = "force-dynamic";

type ShellLayoutProps = {
  children: ReactNode;
};

export default function ShellLayout({ children }: ShellLayoutProps) {
  return <AppShell apiBaseUrl={getApiBaseUrl()}>{children}</AppShell>;
}
