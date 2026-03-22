# Task 04: Upload Registry and Raw File Ingestion API

## Whole-picture context

Users start by uploading raw files. The system needs to register those files, store them, and prepare them for mapping and normalization.

## Specific task goal

Implement backend APIs for file upload and upload-job tracking.

## Requirements

- Create an `UploadJob` model or equivalent tracking table.
- Support CSV and XLSX upload.
- Save uploaded files to a local mounted volume.
- Store metadata for original filename, file type, upload time, status, and inferred source kind when possible.
- Add API endpoints to upload a file, list uploads, and get upload detail.
- Validate basic file type and size.

## Output

A raw ingestion API with upload tracking.

## Acceptance criteria

- A user can upload a file through the API.
- The file is persisted on disk.
- An upload job row is stored in Postgres.
- Status is visible through the API.
- Unsupported file types are rejected cleanly.
