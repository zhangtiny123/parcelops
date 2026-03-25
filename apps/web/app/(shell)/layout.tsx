import type { ReactNode } from "react";

import { AppShell } from "../_components/app-shell";
import { getPublicApiBaseUrl } from "../_lib/api";

export const dynamic = "force-dynamic";

type ShellLayoutProps = {
  children: ReactNode;
};

export default function ShellLayout({ children }: ShellLayoutProps) {
  return <AppShell apiBaseUrl={getPublicApiBaseUrl()}>{children}</AppShell>;
}
