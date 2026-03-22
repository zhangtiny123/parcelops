# Project Overview

This project is a step-by-step implementation of ParcelOps Recovery Copilot.

The goal is to build a focused demo product for an AI-powered ecommerce operations platform that ingests parcel and 3PL data, detects billing errors and operational waste, explains what happened, and automates recovery actions.

## Product name

ParcelOps Recovery Copilot

## Core promise

A user uploads parcel invoices, shipment event files, order reference files, and 3PL billing files. The system normalizes messy data, detects likely overbilling and operational inefficiencies, shows recoverable dollars, explains the issues, and helps generate dispute-ready recovery actions.

## Core user journey

1. Upload raw files.
2. Map columns if needed.
3. Run normalization.
4. Run anomaly detection.
5. Review the dashboard and issue list.
6. Open evidence on shipment, invoice, or issue detail pages.
7. Ask the AI copilot grounded questions over uploaded data.
8. Create a dispute or recovery case.
9. Export or copy a draft dispute summary.

## In-scope MVP features

- File upload for CSV and XLSX
- Basic schema mapping
- Canonical normalized data model
- Deterministic anomaly detection
- Dashboard and issue drill-down
- AI copilot over internal tools and data
- Case creation and dispute draft generation
- Docker Compose local deployment
- Seed synthetic data
- Basic tracing and evals
