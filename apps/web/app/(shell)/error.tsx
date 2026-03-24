"use client";

type ShellErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ShellError({ error, reset }: ShellErrorProps) {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div className="page-header-copy">
          <p className="page-eyebrow">Shell Error</p>
          <h1 className="page-title">The operator workspace could not render.</h1>
          <p className="page-description">
            The application shell is online, but this route failed while
            assembling its data or layout.
          </p>
        </div>
      </section>

      <section className="content-grid content-grid--two">
        <div className="span-12">
          <div className="empty-state empty-state--danger">
            <h2 className="empty-title">Render failure</h2>
            <p className="empty-description">{error.message}</p>
            <div className="button-row">
              <button className="button button-primary" onClick={reset} type="button">
                Try again
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
