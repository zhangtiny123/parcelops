import type { ReactNode } from "react";

type PageHeaderProps = {
  children?: ReactNode;
  description: string;
  eyebrow: string;
  title: string;
};

export function PageHeader({
  children,
  description,
  eyebrow,
  title,
}: PageHeaderProps) {
  return (
    <section className="page-header">
      <div className="page-header-copy">
        <p className="page-eyebrow">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {children ? children : null}
    </section>
  );
}
