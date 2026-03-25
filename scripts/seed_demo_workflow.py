#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_DATASET_DIR = REPO_ROOT / "data" / "generated"
FINAL_UPLOAD_STATUSES = {
    "normalized",
    "normalized_with_errors",
    "normalization_failed",
}


class DemoWorkflowError(RuntimeError):
    """Raised when the seeded demo workflow cannot be completed."""


@dataclass(frozen=True)
class DemoUploadFile:
    file_name: str
    source_kind: str


DEMO_UPLOAD_ORDER = (
    DemoUploadFile("orders.csv", "order"),
    DemoUploadFile("shipments.csv", "shipment"),
    DemoUploadFile("shipment_events.csv", "shipment_event"),
    DemoUploadFile("parcel_invoice_lines.csv", "parcel_invoice"),
    DemoUploadFile("three_pl_invoice_lines.csv", "three_pl_invoice"),
    DemoUploadFile("rate_card_rules.csv", "rate_card"),
)


def build_api_url(api_base_url: str, path: str) -> str:
    normalized_base = api_base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}"


def extract_error_detail(raw_payload: str) -> str:
    if not raw_payload:
        return "No error payload returned."

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return raw_payload

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail

    return raw_payload


def request_json(
    api_base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> Any:
    body: bytes | None = None
    request_headers = {"Accept": "application/json"}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    if headers:
        request_headers.update(headers)

    url = build_api_url(api_base_url, path)
    http_request = request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            raw_payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw_payload = exc.read().decode("utf-8", errors="replace")
        detail = extract_error_detail(raw_payload)
        raise DemoWorkflowError(
            f"{method} {url} failed with status {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise DemoWorkflowError(f"{method} {url} failed: {reason}") from exc

    if raw_payload == "":
        return None

    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise DemoWorkflowError(f"{method} {url} returned invalid JSON.") from exc


def guess_content_type(file_path: Path) -> str:
    if file_path.suffix.lower() == ".csv":
        return "text/csv"
    if file_path.suffix.lower() == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def upload_file(
    api_base_url: str,
    file_path: Path,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    boundary = f"parcelops-demo-{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {guess_content_type(file_path)}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    url = build_api_url(api_base_url, "/uploads")
    http_request = request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            raw_payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw_payload = exc.read().decode("utf-8", errors="replace")
        detail = extract_error_detail(raw_payload)
        raise DemoWorkflowError(
            f"POST {url} failed with status {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise DemoWorkflowError(f"POST {url} failed: {reason}") from exc

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise DemoWorkflowError(f"POST {url} returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise DemoWorkflowError(f"POST {url} returned an unexpected payload.")

    return payload


def wait_for_api(
    api_base_url: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: int,
) -> None:
    print(f"==> Waiting for API health at {build_api_url(api_base_url, '/health')}")
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            payload = request_json(
                api_base_url,
                "/health",
                timeout_seconds=5,
            )
        except DemoWorkflowError as exc:
            last_error = str(exc)
            time.sleep(poll_interval_seconds)
            continue

        if isinstance(payload, dict) and payload.get("status") == "ok":
            print("   API is healthy.")
            return

        last_error = "API health endpoint did not report status=ok."
        time.sleep(poll_interval_seconds)

    raise DemoWorkflowError(last_error or "API did not become healthy before timeout.")


def assert_dataset_files_exist(dataset_dir: Path) -> None:
    missing_files = [
        demo_file.file_name
        for demo_file in DEMO_UPLOAD_ORDER
        if not (dataset_dir / demo_file.file_name).is_file()
    ]

    if missing_files:
        raise DemoWorkflowError(
            "Dataset directory is missing required files: "
            + ", ".join(sorted(missing_files))
        )


def ensure_backend_is_clean(
    api_base_url: str,
    *,
    allow_existing: bool,
    timeout_seconds: int,
) -> None:
    uploads = request_json(
        api_base_url,
        "/uploads",
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(uploads, list):
        raise DemoWorkflowError("GET /uploads returned an unexpected payload.")

    if uploads and not allow_existing:
        raise DemoWorkflowError(
            "The backend already has uploaded files. Start from a clean database "
            "(for example `docker compose down -v`) or rerun with --allow-existing."
        )


def build_mapping_payload(
    source_kind: str,
    preview: dict[str, Any],
    suggestion: dict[str, Any],
) -> dict[str, Any]:
    columns = preview.get("columns")
    canonical_fields = suggestion.get("canonical_fields")
    suggested_mappings = suggestion.get("suggested_mappings")

    if not isinstance(columns, list):
        raise DemoWorkflowError("Upload preview did not include columns.")
    if not isinstance(canonical_fields, list):
        raise DemoWorkflowError("Suggested mapping did not include canonical fields.")
    if not isinstance(suggested_mappings, list):
        raise DemoWorkflowError("Suggested mapping did not include suggested mappings.")

    available_columns = {str(column) for column in columns}
    mapping_rows: list[dict[str, str]] = []
    used_canonical_fields: set[str] = set()

    for mapping in suggested_mappings:
        if not isinstance(mapping, dict):
            continue

        source_column = mapping.get("source_column")
        canonical_field = mapping.get("canonical_field")
        if not isinstance(source_column, str) or not isinstance(canonical_field, str):
            continue
        if source_column not in available_columns:
            continue
        if canonical_field in used_canonical_fields:
            continue

        mapping_rows.append(
            {
                "source_column": source_column,
                "canonical_field": canonical_field,
            }
        )
        used_canonical_fields.add(canonical_field)

    # Exact header matches are safe fallbacks when the suggestion set is incomplete.
    for field in canonical_fields:
        if not isinstance(field, dict):
            continue

        field_name = field.get("name")
        if not isinstance(field_name, str):
            continue
        if field_name in used_canonical_fields:
            continue
        if field_name not in available_columns:
            continue

        mapping_rows.append(
            {
                "source_column": field_name,
                "canonical_field": field_name,
            }
        )
        used_canonical_fields.add(field_name)

    missing_required_fields = [
        str(field.get("label") or field.get("name"))
        for field in canonical_fields
        if isinstance(field, dict)
        and field.get("required") is True
        and isinstance(field.get("name"), str)
        and field["name"] not in used_canonical_fields
    ]

    if missing_required_fields:
        raise DemoWorkflowError(
            f"{source_kind} is missing required mappings: "
            + ", ".join(sorted(missing_required_fields))
        )

    return {
        "source_kind": source_kind,
        "mappings": mapping_rows,
    }


def poll_upload_until_finished(
    api_base_url: str,
    upload_id: str,
    file_name: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status: str | None = None

    while time.monotonic() < deadline:
        upload = request_json(
            api_base_url,
            f"/uploads/{upload_id}",
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(upload, dict):
            raise DemoWorkflowError(
                f"{file_name} returned an unexpected upload payload."
            )

        status = upload.get("status")
        if not isinstance(status, str):
            raise DemoWorkflowError(
                f"{file_name} did not report a valid upload status."
            )

        if status != last_status:
            print(f"   {file_name}: {status}")
            last_status = status

        if status in FINAL_UPLOAD_STATUSES:
            return upload

        time.sleep(poll_interval_seconds)

    raise DemoWorkflowError(
        f"{file_name} did not finish normalization before the timeout expired."
    )


def seed_upload(
    api_base_url: str,
    dataset_dir: Path,
    demo_file: DemoUploadFile,
    *,
    poll_interval_seconds: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    file_path = dataset_dir / demo_file.file_name
    print(f"==> Processing {demo_file.file_name}")

    upload = upload_file(
        api_base_url,
        file_path,
        timeout_seconds=timeout_seconds,
    )
    upload_id = upload.get("id")
    if not isinstance(upload_id, str) or upload_id == "":
        raise DemoWorkflowError(f"{demo_file.file_name} upload did not return an id.")

    preview = request_json(
        api_base_url,
        f"/uploads/{upload_id}/preview",
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(preview, dict):
        raise DemoWorkflowError(
            f"{demo_file.file_name} preview returned an unexpected payload."
        )

    source_kind_query = parse.urlencode({"source_kind": demo_file.source_kind})
    suggestion = request_json(
        api_base_url,
        f"/uploads/{upload_id}/suggested-mapping?{source_kind_query}",
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(suggestion, dict):
        raise DemoWorkflowError(
            f"{demo_file.file_name} suggested mapping returned an unexpected payload."
        )

    selected_source_kind = suggestion.get("source_kind")
    if selected_source_kind != demo_file.source_kind:
        raise DemoWorkflowError(
            f"{demo_file.file_name} resolved source kind "
            f"{selected_source_kind!r}, expected {demo_file.source_kind!r}."
        )

    mapping_payload = build_mapping_payload(demo_file.source_kind, preview, suggestion)
    request_json(
        api_base_url,
        f"/uploads/{upload_id}/mapping",
        method="PUT",
        payload=mapping_payload,
        timeout_seconds=timeout_seconds,
    )
    request_json(
        api_base_url,
        f"/uploads/{upload_id}/normalize",
        method="POST",
        timeout_seconds=timeout_seconds,
    )

    final_upload = poll_upload_until_finished(
        api_base_url,
        upload_id,
        demo_file.file_name,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )

    final_status = final_upload.get("status")
    if final_status == "normalization_failed":
        raise DemoWorkflowError(
            f"{demo_file.file_name} failed normalization: "
            f"{final_upload.get('last_error') or 'unknown error'}"
        )

    normalized_row_count = int(final_upload.get("normalized_row_count") or 0)
    normalization_error_count = int(final_upload.get("normalization_error_count") or 0)
    print(
        "   "
        f"{demo_file.file_name}: {normalized_row_count} rows normalized, "
        f"{normalization_error_count} errors."
    )
    return final_upload


def run_issue_detection(
    api_base_url: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    print("==> Running issue detection")
    detection = request_json(
        api_base_url,
        "/issues/detect",
        method="POST",
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(detection, dict):
        raise DemoWorkflowError("Issue detection returned an unexpected payload.")
    return detection


def print_detection_summary(detection: dict[str, Any]) -> None:
    total_issue_count = int(detection.get("total_issue_count") or 0)
    created_count = int(detection.get("created_count") or 0)
    unchanged_count = int(detection.get("unchanged_count") or 0)
    print(
        "   "
        f"Detected {total_issue_count} issues "
        f"(created={created_count}, unchanged={unchanged_count})."
    )

    counts_by_issue_type = detection.get("counts_by_issue_type")
    if not isinstance(counts_by_issue_type, dict):
        return

    for issue_type, count in sorted(counts_by_issue_type.items()):
        print(f"   - {issue_type}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load the seeded ParcelOps demo dataset through the uploads API, "
            "run normalization in the correct order, and trigger issue detection."
        )
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"Base URL for the ParcelOps API. Default: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help=f"Directory containing demo CSV files. Default: {DEFAULT_DATASET_DIR}",
    )
    parser.add_argument(
        "--wait-for-api",
        action="store_true",
        help="Wait for the API health endpoint before seeding the workflow.",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow uploads to be added even if the backend already contains upload jobs.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=2.0,
        help="Polling interval while waiting for normalization to finish.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Timeout for API waits and long-running workflow steps.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()

    try:
        assert_dataset_files_exist(dataset_dir)

        if args.wait_for_api:
            wait_for_api(
                args.api_base_url,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )

        ensure_backend_is_clean(
            args.api_base_url,
            allow_existing=args.allow_existing,
            timeout_seconds=args.timeout_seconds,
        )

        for demo_file in DEMO_UPLOAD_ORDER:
            seed_upload(
                args.api_base_url,
                dataset_dir,
                demo_file,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )

        detection = run_issue_detection(
            args.api_base_url,
            timeout_seconds=args.timeout_seconds,
        )
        print_detection_summary(detection)
    except DemoWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("==> Seeded demo workflow completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
