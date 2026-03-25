from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.copilot.eval_fixture import seed_copilot_eval_records
from app.copilot.evals import (
    CopilotEvalCase,
    CopilotEvalDataset,
    CopilotEvalExpectation,
    CopilotEvalToolCallExpectation,
    load_copilot_eval_dataset,
    render_copilot_eval_report,
    run_copilot_eval_cases,
)
from app.settings import get_settings, reset_settings_cache
from conftest import run_migrations


def _prepare_eval_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    database_name: str,
) -> str:
    database_url = f"sqlite:///{tmp_path / database_name}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("COPILOT_PROVIDER", "heuristic")
    reset_settings_cache()
    run_migrations(database_url)

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            seed_copilot_eval_records(db)
    finally:
        engine.dispose()

    return database_url


def test_copilot_eval_dataset_stays_within_expected_size() -> None:
    dataset = load_copilot_eval_dataset()

    assert 15 <= len(dataset.cases) <= 20
    assert len({case.id for case in dataset.cases}) == len(dataset.cases)
    assert all(case.question for case in dataset.cases)
    assert all(case.scoring_notes for case in dataset.cases)


def test_copilot_eval_harness_runs_full_dataset_and_reports_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_eval_database(
        tmp_path,
        monkeypatch,
        database_name="copilot-eval-harness.db",
    )
    dataset = load_copilot_eval_dataset()
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)

    try:
        run_result = run_copilot_eval_cases(
            dataset=dataset,
            cases=dataset.cases,
            session_factory=session_factory,
            settings=replace(get_settings(), copilot_provider="heuristic"),
        )
    finally:
        engine.dispose()

    report = render_copilot_eval_report(run_result)

    assert run_result.total_case_count == len(dataset.cases)
    assert run_result.passed_case_count == len(dataset.cases)
    assert run_result.failed_case_count == 0
    assert run_result.high_risk_case_count == 0
    assert "Copilot Eval Harness" in report
    assert "unsupported_weather" in report
    assert "0 failed" in report


def test_copilot_eval_harness_surfaces_failing_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = _prepare_eval_database(
        tmp_path,
        monkeypatch,
        database_name="copilot-eval-harness-failing.db",
    )
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    dataset = CopilotEvalDataset(
        name="failing-case-dataset",
        description="Synthetic dataset used to prove failure reporting.",
        cases=(
            CopilotEvalCase(
                id="forced_failure",
                category="issues",
                question="Which open issues represent the highest recoverable amount right now?",
                scoring_notes="This case intentionally expects impossible output to confirm failure reporting.",
                expected=CopilotEvalExpectation(
                    status="completed",
                    tool_calls=(
                        CopilotEvalToolCallExpectation(
                            name="search_issues",
                            arguments={
                                "intent": "top_recovery",
                                "status": "open",
                                "sort_by": "recoverable_amount_desc",
                            },
                        ),
                    ),
                    correctness_must_include=("issue-999", "$99.99"),
                    groundedness_must_include=("issue-999",),
                    required_reference_ids=("issue-999",),
                    forbidden_fragments=("issue-1",),
                    min_reference_count=1,
                ),
            ),
        ),
    )

    try:
        run_result = run_copilot_eval_cases(
            dataset=dataset,
            cases=dataset.cases,
            session_factory=session_factory,
            settings=replace(get_settings(), copilot_provider="heuristic"),
        )
    finally:
        engine.dispose()

    case_result = run_result.case_results[0]

    assert run_result.failed_case_count == 1
    assert not case_result.passed
    assert case_result.hallucination_risk == "high"
    assert any("issue-999" in failure for failure in case_result.failures)
