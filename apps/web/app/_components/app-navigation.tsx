"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  {
    detail: "Recovery and system overview",
    href: "/dashboard",
    label: "Dashboard",
    shortLabel: "DB",
  },
  {
    detail: "Source files and normalization",
    href: "/uploads",
    label: "Uploads",
    shortLabel: "UP",
  },
  {
    detail: "Detected anomalies and evidence",
    href: "/issues",
    label: "Issues",
    shortLabel: "IS",
  },
  {
    detail: "Grounded operational analysis",
    href: "/copilot",
    label: "Copilot",
    shortLabel: "AI",
  },
  {
    detail: "Dispute-ready recovery cases",
    href: "/cases",
    label: "Cases",
    shortLabel: "CS",
  },
];

function isActivePath(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppNavigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="sidebar-nav">
      {navigationItems.map((item) => (
        <Link
          className={`nav-link ${isActivePath(pathname, item.href) ? "is-active" : ""}`}
          href={item.href}
          key={item.href}
        >
          <span className="nav-kicker">{item.shortLabel}</span>
          <span className="nav-copy">
            <span className="nav-label">{item.label}</span>
            <span className="nav-detail">{item.detail}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}
