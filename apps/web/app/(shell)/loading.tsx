export default function ShellLoading() {
  return (
    <div className="page-stack" aria-busy="true" aria-live="polite">
      <section className="page-header">
        <div className="page-header-copy">
          <div className="loading-line" style={{ width: "8rem" }} />
          <div className="loading-line loading-line--title" />
          <div className="loading-line loading-line--body" />
        </div>
        <p className="workflow-note">
          Loading live ParcelOps data and rebuilding the demo workspace.
        </p>
      </section>

      <section className="metric-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="loading-block" key={index} />
        ))}
      </section>

      <section className="content-grid content-grid--wide">
        <div className="loading-block span-7" style={{ minHeight: "20rem" }} />
        <div className="loading-block span-5" style={{ minHeight: "20rem" }} />
      </section>
    </div>
  );
}
