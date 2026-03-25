from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
import tempfile

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import get_settings

from .eval_fixture import seed_copilot_eval_records
from .evals import (
    DEFAULT_EVAL_DATASET_PATH,
    load_copilot_eval_dataset,
    render_copilot_eval_report,
    run_copilot_eval_cases,
    select_copilot_eval_cases,
)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Run the ParcelOps copilot eval harness.")
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        default=[],
        help="Run only the specified eval case id. May be supplied multiple times.",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_EVAL_DATASET_PATH),
        help="Path to the eval dataset JSON file.",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format for eval results.",
    )
    parser.add_argument(
        "--database-file",
        help="Optional SQLite database path to preserve after the run for debugging.",
    )
    args = parser.parse_args(argv)

    dataset = load_copilot_eval_dataset(Path(args.dataset).resolve())
    cases = select_copilot_eval_cases(dataset, args.case_ids)

    database_path, should_cleanup = _resolve_database_path(args.database_file)
    database_url = f"sqlite:///{database_path}"
    _run_migrations(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            seed_copilot_eval_records(db)

        session_factory = sessionmaker(bind=engine)
        settings = replace(get_settings(), copilot_provider="heuristic")
        run_result = run_copilot_eval_cases(
            dataset=dataset,
            cases=cases,
            session_factory=session_factory,
            settings=settings,
        )

        if args.format == "json":
            print(run_result.to_json())
        else:
            print(render_copilot_eval_report(run_result))

        return 0 if run_result.failed_case_count == 0 else 1
    finally:
        engine.dispose()
        if should_cleanup and database_path.exists():
            database_path.unlink()


def _resolve_database_path(database_file: str | None) -> tuple[Path, bool]:
    if database_file:
        database_path = Path(database_file).expanduser().resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if database_path.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing eval database file: {database_path}"
            )
        return database_path, False

    handle = tempfile.NamedTemporaryFile(
        suffix=".db", prefix="copilot-evals-", delete=False
    )
    handle.close()
    return Path(handle.name), True


def _run_migrations(database_url: str) -> None:
    api_root = Path(__file__).resolve().parents[2]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


if __name__ == "__main__":
    raise SystemExit(main())
