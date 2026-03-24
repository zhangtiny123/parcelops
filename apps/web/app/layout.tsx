import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: {
    default: "ParcelOps Recovery Copilot",
    template: "%s | ParcelOps Recovery Copilot",
  },
  description:
    "Operator workspace for upload intake, issue detection, and recovery case management.",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
