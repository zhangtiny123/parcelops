const statusCards = [
  {
    label: "Web",
    value: "running",
    detail: "Next.js placeholder shell is online.",
  },
  {
    label: "API",
    value: "expected",
    detail: "FastAPI health endpoint is wired through Compose.",
  },
  {
    label: "Worker",
    value: "expected",
    detail: "Celery worker boots against Redis for async jobs.",
  },
];

export default function HomePage() {
  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">ParcelOps Recovery Copilot</p>
        <h1>Bootstrap stack is ready for feature work.</h1>
        <p className="lede">
          This placeholder interface confirms the local runtime foundation for
          the web app, API, worker, Postgres, and Redis.
        </p>
      </section>

      <section className="grid" aria-label="Bootstrap service status">
        {statusCards.map((card) => (
          <article className="card" key={card.label}>
            <p className="card-label">{card.label}</p>
            <p className="card-value">{card.value}</p>
            <p className="card-detail">{card.detail}</p>
          </article>
        ))}
      </section>

      <section className="panel">
        <div>
          <p className="panel-label">Configured API base URL</p>
          <code>{apiBaseUrl}</code>
        </div>
        <a className="panel-link" href={`${apiBaseUrl}/health`}>
          Check API health
        </a>
      </section>
    </main>
  );
}
