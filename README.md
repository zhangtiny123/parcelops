# ParcelOps Recovery Copilot

ParcelOps Recovery Copilot is a local-first demo product for detecting parcel and 3PL billing errors, explaining what happened, and helping operators turn findings into recovery actions.

The stack includes:

- `web`: Next.js operator workspace at `http://localhost:3000`
- `api`: FastAPI backend at `http://localhost:8000`
- `worker`: Celery worker for normalization jobs
- `postgres`: PostgreSQL persistence
- `redis`: Redis broker and cache

## Fastest Demo Path

For the clean-machine walkthrough, use the one-command demo bootstrap:

```bash
./scripts/demo-up.sh
```

That helper will:

1. Create `.env` from `.env.example` if needed.
2. Regenerate the seeded demo dataset into `data/generated/`.
3. Start Docker Compose in detached mode.
4. Upload the sample files through the API.
5. Save suggested mappings.
6. Normalize the files in dependency-safe order.
7. Run issue detection.

When it finishes, open:

- Web UI: `http://localhost:3000`
- Web health: `http://localhost:3000/health`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

To reset the demo data and start over from a blank database:

```bash
docker compose down -v
```

Then run `./scripts/demo-up.sh` again.

## Demo Walkthrough

After `./scripts/demo-up.sh`, the product story is ready to walk through:

1. Open `/dashboard` to confirm API health, recent uploads, and recoverable totals.
2. Open `/uploads` to show the seeded files, their source kinds, and completed normalization states.
3. Open `/issues` to review the detected anomalies and create a recovery case from selected issues.
4. Open `/cases` to refine the generated dispute drafts and internal notes.
5. Open `/copilot` to ask grounded questions against the detected issue set.

The seeded demo flow should produce 18 issues with this breakdown:

- `duplicate_charge`: 4
- `billed_weight_mismatch`: 4
- `zone_mismatch`: 3
- `incorrect_unit_rate_vs_rate_card`: 3
- `invoice_line_without_matched_order_or_shipment`: 2
- `invoice_line_without_matched_shipment`: 2

## Environment Config

Copy the template if you want to review or customize local settings:

```bash
cp .env.example .env
```

The most relevant variables for demo runs are:

- `WEB_PORT`: host port for the Next.js app
- `API_PORT`: host port for the FastAPI service
- `NEXT_PUBLIC_API_BASE_URL`: browser-visible API base URL for the web app
- `DATABASE_URL`: database connection string used by the API and worker
- `LOCAL_STORAGE_ROOT`: mounted upload storage path inside the containers
- `COPILOT_PROVIDER`: defaults to `heuristic`

The default copilot mode is `heuristic`, so the demo does not require an external API key.

## Manual Setup

If you want to bring the stack up step by step instead of using `./scripts/demo-up.sh`:

1. Copy the environment template.

   ```bash
   cp .env.example .env
   ```

2. Start the stack.

   ```bash
   docker compose up --build -d
   ```

3. Confirm the core services are healthy.

   - Web: `http://localhost:3000/health`
   - API: `http://localhost:8000/health`
   - API docs: `http://localhost:8000/docs`

4. Regenerate the sample dataset if you want a fresh copy.

   ```bash
   ./scripts/generate-demo-dataset.sh
   ```

5. Load the seeded walkthrough data through the API.

   ```bash
   python3 scripts/seed_demo_workflow.py --wait-for-api
   ```

The seeded loader expects an empty uploads table by default. If you already loaded demo data, reset with `docker compose down -v` before rerunning it.

## Dataset Generation

The synthetic demo dataset is reproducible and stays stable by default:

```bash
./scripts/generate-demo-dataset.sh
```

The default seed is `20260323`. Generated files are written to `data/generated/`:

- `orders.csv`
- `shipments.csv`
- `shipment_events.csv`
- `parcel_invoice_lines.csv`
- `three_pl_invoice_lines.csv`
- `rate_card_rules.csv`

To write the output somewhere else or use a different seed:

```bash
./scripts/generate-demo-dataset.sh --seed 20260401 --output-dir /tmp/parcelops-demo
```

## Manual Upload Walkthrough

If you want to show ingestion interactively in the browser instead of using the seeded loader, use the files in `data/generated/` and upload them in this order:

1. `orders.csv`
2. `shipments.csv`
3. `shipment_events.csv`
4. `parcel_invoice_lines.csv`
5. `three_pl_invoice_lines.csv`
6. `rate_card_rules.csv`

For each file:

1. Upload it from `/uploads`.
2. Confirm the suggested source kind.
3. Save the mapping.
4. Run normalization and wait for the upload to finish.

After all files are normalized, open `/issues` and click `Run issue detection`.

## Copilot Usage

The copilot page is available at `/copilot`.

- The default `heuristic` provider works out of the box for demos.
- Starter prompts are built in for top recoveries, provider spend shifts, and high-confidence billing errors.
- The best results come after the seeded uploads have been normalized and issue detection has been run.

Useful first prompts:

- `Which open issues represent the highest recoverable amount right now?`
- `Explain which providers have the sharpest recovery-cost increase this month.`
- `Show the billing errors with the strongest confidence and the evidence behind them.`

## Helper Scripts

- `./scripts/demo-up.sh`: end-to-end demo bootstrap from `.env` creation through issue detection
- `./scripts/generate-demo-dataset.sh`: regenerate the seeded demo CSVs
- `python3 scripts/seed_demo_workflow.py --wait-for-api`: load the seeded dataset through the upload API without restarting Compose
- `./scripts/start-deps.sh`: start only Postgres and Redis in Docker
- `./scripts/run-api-local.sh`: run the API locally against the dependency containers
- `./scripts/run-worker-local.sh`: run the worker locally against the dependency containers
- `./scripts/stop-deps.sh`: stop the dependency containers
- `./scripts/run-checks.sh`: run the main API and web checks already wired into the repo

## Run Only Dependencies

If you want to run the API and worker directly on your machine while keeping only Postgres and Redis in Docker:

1. Start the backing services.

   ```bash
   ./scripts/start-deps.sh
   ```

2. Run the API locally.

   ```bash
   ./scripts/run-api-local.sh
   ```

3. Run the worker locally in another terminal.

   ```bash
   ./scripts/run-worker-local.sh
   ```

The local scripts now load `.env` when present and default to the same host ports that Compose publishes:

- Postgres: `localhost:5432`
- Redis: `localhost:6379`

## Repository Layout

```text
apps/
  api/            # FastAPI backend
  web/            # Next.js frontend
  worker/         # Celery worker
packages/
  shared/         # Shared contracts and types when needed
infra/
  postgres/       # Postgres-specific assets
  redis/          # Redis-specific assets
data/
  raw/            # Unmodified source files
  generated/      # Synthetic demo datasets
  uploads/        # Local mounted storage for demo uploads
docs/
  reference/      # Stable project reference
  tasks/          # One file per implementation task
scripts/          # Helper scripts and generators
docker-compose.yml
.env.example
```

## Subsystem Docs

- Web: [apps/web/README.md](apps/web/README.md)
- API: [apps/api/README.md](apps/api/README.md)
- Worker: [apps/worker/README.md](apps/worker/README.md)
- Reference docs: [docs/reference/README.md](docs/reference/README.md)
- Task index: [docs/tasks/README.md](docs/tasks/README.md)
