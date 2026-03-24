import Link from "next/link";
import type { ReactNode } from "react";

import { AppNavigation } from "./app-navigation";

type AppShellProps = {
  apiBaseUrl: string;
  children: ReactNode;
};

export function AppShell({ apiBaseUrl, children }: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-panel">
          <p className="brand-label">ParcelOps</p>
          <p className="brand-title">Recovery Copilot</p>
          <p className="brand-copy">
            Operator workspace for upload intake, anomaly review, and dispute
            preparation.
          </p>
        </div>

        <AppNavigation />

        <div className="sidebar-footer">
          <p className="brand-label">Configured API base URL</p>
          <code>{apiBaseUrl}</code>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-copy">
            <p className="topbar-label">Frontend shell</p>
            <p className="topbar-title">Operations control room</p>
          </div>
          <div className="topbar-chip-group">
            <span className="chip chip-muted">Next.js shell</span>
            <span className="chip">API-linked</span>
            <Link className="chip" href="/dashboard">
              Current workspace
            </Link>
          </div>
        </header>

        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
