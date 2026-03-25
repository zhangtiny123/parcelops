"use client";

import { useEffect, useRef, useState } from "react";

import { EmptyState, MetricCard, SectionCard, StatusBadge } from "../../_components/ui";
import type {
  ColumnMapping,
  UploadJob,
  UploadPreview,
  UploadSuggestedMapping,
} from "../../_lib/api-types";
import {
  formatBytes,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatStatusLabel,
} from "../../_lib/format";
import {
  getBrowserSuggestedMapping,
  getBrowserUpload,
  getBrowserUploadPreview,
  listBrowserUploads,
  saveBrowserUploadMapping,
  triggerBrowserUploadNormalization,
  uploadBrowserFile,
} from "../../_lib/uploads-client";

type UploadWorkflowProps = {
  initialUploads: UploadJob[];
  initialUploadsError: string | null;
};

type MappingDraft = Record<string, string>;
type NoticeTone = "danger" | "good" | "warning";

const POLLABLE_UPLOAD_STATUSES = new Set([
  "normalization_queued",
  "normalizing",
]);

function buildStatusCounts(statuses: string[]) {
  return statuses.reduce<Record<string, number>>((counts, status) => {
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
}

function buildDraftFromMappings(
  columns: string[],
  mappings: ColumnMapping[],
): MappingDraft {
  const draft = columns.reduce<MappingDraft>((nextDraft, column) => {
    nextDraft[column] = "";
    return nextDraft;
  }, {});

  for (const mapping of mappings) {
    if (mapping.source_column in draft) {
      draft[mapping.source_column] = mapping.canonical_field;
    }
  }

  return draft;
}

function buildDraftFromSuggestedMapping(
  columns: string[],
  suggestedMapping: UploadSuggestedMapping,
) {
  return buildDraftFromMappings(
    columns,
    suggestedMapping.saved_mapping?.mappings ?? suggestedMapping.suggested_mappings,
  );
}

function buildMappingsFromDraft(
  columns: string[],
  draft: MappingDraft,
): ColumnMapping[] {
  return columns.flatMap((column) => {
    const canonicalField = draft[column];

    if (!canonicalField) {
      return [];
    }

    return [
      {
        canonical_field: canonicalField,
        source_column: column,
      },
    ];
  });
}

function sameMappings(left: ColumnMapping[], right: ColumnMapping[]) {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((mapping, index) => {
    const rightMapping = right[index];

    return (
      mapping.source_column === rightMapping?.source_column &&
      mapping.canonical_field === rightMapping?.canonical_field
    );
  });
}

function sortUploadsByNewest(uploads: UploadJob[]) {
  return [...uploads].sort((left, right) => {
    return Date.parse(right.uploaded_at) - Date.parse(left.uploaded_at);
  });
}

function upsertUpload(existingUploads: UploadJob[], nextUpload: UploadJob) {
  return sortUploadsByNewest(
    existingUploads.filter((upload) => upload.id !== nextUpload.id).concat(nextUpload),
  );
}

function resolveSelectedUploadId(
  uploads: UploadJob[],
  currentSelectedUploadId: string | null,
  preferredUploadId?: string,
) {
  if (preferredUploadId && uploads.some((upload) => upload.id === preferredUploadId)) {
    return preferredUploadId;
  }

  if (
    currentSelectedUploadId &&
    uploads.some((upload) => upload.id === currentSelectedUploadId)
  ) {
    return currentSelectedUploadId;
  }

  return uploads[0]?.id ?? null;
}

function buildRequiredFieldList(
  suggestedMapping: UploadSuggestedMapping | null,
  draftMappings: ColumnMapping[],
) {
  const mappedFields = new Set(
    draftMappings.map((mapping) => mapping.canonical_field).filter(Boolean),
  );

  return (suggestedMapping?.canonical_fields ?? []).filter((field) => {
    return field.required && !mappedFields.has(field.name);
  });
}

function buildSavedMappingState(
  suggestedMapping: UploadSuggestedMapping | null,
  draftMappings: ColumnMapping[],
  selectedSourceKind: string,
) {
  if (!suggestedMapping?.saved_mapping) {
    return false;
  }

  return (
    suggestedMapping.saved_mapping.source_kind === selectedSourceKind &&
    sameMappings(suggestedMapping.saved_mapping.mappings, draftMappings)
  );
}

export function UploadWorkflow({
  initialUploads,
  initialUploadsError,
}: UploadWorkflowProps) {
  const [isHydrated, setIsHydrated] = useState(false);
  const [uploads, setUploads] = useState<UploadJob[]>(initialUploads);
  const [uploadsError, setUploadsError] = useState<string | null>(initialUploadsError);
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(
    initialUploads[0]?.id ?? null,
  );
  const [selectedUploadPreview, setSelectedUploadPreview] =
    useState<UploadPreview | null>(null);
  const [selectedUploadMapping, setSelectedUploadMapping] =
    useState<UploadSuggestedMapping | null>(null);
  const [mappingDraft, setMappingDraft] = useState<MappingDraft>({});
  const [selectedSourceKind, setSelectedSourceKind] = useState("");
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ text: string; tone: NoticeTone } | null>(null);
  const [isLoadingSelection, setIsLoadingSelection] = useState(false);
  const [isRefreshingUploads, setIsRefreshingUploads] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSavingMapping, setIsSavingMapping] = useState(false);
  const [isNormalizing, setIsNormalizing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadStatusRef = useRef<Record<string, string>>({});

  const selectedUpload =
    uploads.find((upload) => upload.id === selectedUploadId) ?? null;
  const selectedUploadStatus = selectedUpload?.status ?? null;
  const shouldPollSelectedUpload =
    selectedUploadStatus !== null &&
    POLLABLE_UPLOAD_STATUSES.has(selectedUploadStatus);

  const draftMappings = buildMappingsFromDraft(
    selectedUploadPreview?.columns ?? [],
    mappingDraft,
  );
  const missingRequiredFields = buildRequiredFieldList(
    selectedUploadMapping,
    draftMappings,
  );
  const mappingIsSaved = buildSavedMappingState(
    selectedUploadMapping,
    draftMappings,
    selectedSourceKind,
  );
  const statusCounts = buildStatusCounts(uploads.map((upload) => upload.status));
  const completedCount =
    (statusCounts.normalized ?? 0) + (statusCounts.normalized_with_errors ?? 0);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  function formatWorkflowDateTime(value: string | null | undefined) {
    return formatDateTime(value, isHydrated ? undefined : { timeZone: "UTC" });
  }

  useEffect(() => {
    if (!selectedUploadId) {
      setSelectedUploadPreview(null);
      setSelectedUploadMapping(null);
      setMappingDraft({});
      setSelectedSourceKind("");
      setSelectionError(null);
      return;
    }

    const uploadId = selectedUploadId;
    let cancelled = false;

    async function loadSelection() {
      setIsLoadingSelection(true);
      setSelectionError(null);
      setSelectedUploadPreview(null);
      setSelectedUploadMapping(null);
      setMappingDraft({});

      const [uploadResult, previewResult, mappingResult] = await Promise.all([
        getBrowserUpload(uploadId),
        getBrowserUploadPreview(uploadId),
        getBrowserSuggestedMapping(uploadId),
      ]);

      if (cancelled) {
        return;
      }

      if (uploadResult.data) {
        setUploads((currentUploads) => upsertUpload(currentUploads, uploadResult.data));
      }

      if (!previewResult.data || !mappingResult.data) {
        setSelectionError(previewResult.error ?? mappingResult.error ?? "Unable to load the selected upload.");
        setSelectedUploadPreview(null);
        setSelectedUploadMapping(null);
        setMappingDraft({});
        setSelectedSourceKind("");
        setIsLoadingSelection(false);
        return;
      }

      setSelectedUploadPreview(previewResult.data);
      setSelectedUploadMapping(mappingResult.data);
      setMappingDraft(
        buildDraftFromSuggestedMapping(previewResult.data.columns, mappingResult.data),
      );
      setSelectedSourceKind(
        mappingResult.data.source_kind ?? previewResult.data.inferred_source_kind ?? "",
      );
      setIsLoadingSelection(false);
    }

    void loadSelection();

    return () => {
      cancelled = true;
    };
  }, [selectedUploadId]);

  useEffect(() => {
    if (!selectedUploadId || !shouldPollSelectedUpload) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void (async () => {
        const uploadsResult = await listBrowserUploads();

        if (!uploadsResult.data) {
          setUploadsError(uploadsResult.error);
          return;
        }

        setUploads(uploadsResult.data);
        setUploadsError(null);
        setSelectedUploadId((currentSelectedUploadId) =>
          resolveSelectedUploadId(
            uploadsResult.data,
            currentSelectedUploadId,
            selectedUploadId,
          ),
        );
      })();
    }, 3000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [selectedUploadId, shouldPollSelectedUpload]);

  useEffect(() => {
    if (!selectedUpload) {
      return;
    }

    const previousStatus = uploadStatusRef.current[selectedUpload.id];
    uploadStatusRef.current[selectedUpload.id] = selectedUpload.status;

    if (!previousStatus || previousStatus === selectedUpload.status) {
      return;
    }

    if (selectedUpload.status === "normalized") {
      setNotice({
        text: `${selectedUpload.original_filename} normalized ${formatNumber(
          selectedUpload.normalized_row_count,
        )} row(s).`,
        tone: "good",
      });
    }

    if (selectedUpload.status === "normalized_with_errors") {
      setNotice({
        text: `${selectedUpload.original_filename} finished with ${formatNumber(
          selectedUpload.normalization_error_count,
        )} normalization error(s).`,
        tone: "warning",
      });
    }

    if (selectedUpload.status === "normalization_failed") {
      setNotice({
        text:
          selectedUpload.last_error ??
          `Normalization failed for ${selectedUpload.original_filename}.`,
        tone: "danger",
      });
    }
  }, [selectedUpload]);

  async function refreshUploads(preferredUploadId?: string) {
    setIsRefreshingUploads(true);
    const uploadsResult = await listBrowserUploads();
    setIsRefreshingUploads(false);

    if (!uploadsResult.data) {
      setUploadsError(uploadsResult.error);
      return;
    }

    setUploads(uploadsResult.data);
    setUploadsError(null);
    setSelectedUploadId((currentSelectedUploadId) =>
      resolveSelectedUploadId(
        uploadsResult.data,
        currentSelectedUploadId,
        preferredUploadId,
      ),
    );
  }

  async function handleUploadSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const file = fileInputRef.current?.files?.[0];

    if (!file) {
      setNotice({
        text: "Choose a CSV or XLSX file before submitting.",
        tone: "warning",
      });
      return;
    }

    setIsUploading(true);
    setNotice(null);

    const uploadResult = await uploadBrowserFile(file);

    setIsUploading(false);

    if (!uploadResult.data) {
      setNotice({
        text: uploadResult.error,
        tone: "danger",
      });
      return;
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    setUploads((currentUploads) => upsertUpload(currentUploads, uploadResult.data));
    setUploadsError(null);
    setSelectedUploadId(uploadResult.data.id);
    setNotice({
      text: `${uploadResult.data.original_filename} uploaded. Preview and mapping are ready to review.`,
      tone: "good",
    });

    await refreshUploads(uploadResult.data.id);
  }

  async function handleSourceKindChange(
    event: React.ChangeEvent<HTMLSelectElement>,
  ) {
    if (!selectedUploadId || !selectedUploadPreview) {
      return;
    }

    const nextSourceKind = event.target.value;
    const previousSourceKind = selectedSourceKind;

    setIsLoadingSelection(true);
    setSelectedSourceKind(nextSourceKind);
    setSelectionError(null);

    const mappingResult = await getBrowserSuggestedMapping(
      selectedUploadId,
      nextSourceKind,
    );

    setIsLoadingSelection(false);

    if (!mappingResult.data) {
      setSelectedSourceKind(previousSourceKind);
      setSelectionError(mappingResult.error);
      return;
    }

    setSelectedUploadMapping(mappingResult.data);
    setMappingDraft(
      buildDraftFromSuggestedMapping(
        selectedUploadPreview.columns,
        mappingResult.data,
      ),
    );
    setNotice({
      text: `Mapping suggestions refreshed for ${formatStatusLabel(nextSourceKind)}.`,
      tone: "good",
    });
  }

  async function handleSaveMapping() {
    if (!selectedUploadId || !selectedUploadPreview || !selectedSourceKind) {
      setNotice({
        text: "Choose a source kind before saving mappings.",
        tone: "warning",
      });
      return;
    }

    setIsSavingMapping(true);
    setNotice(null);

    const mappingResult = await saveBrowserUploadMapping(selectedUploadId, {
      mappings: draftMappings,
      source_kind: selectedSourceKind,
    });

    setIsSavingMapping(false);

    if (!mappingResult.data) {
      setNotice({
        text: mappingResult.error,
        tone: "danger",
      });
      return;
    }

    setSelectedUploadMapping((currentMapping) => {
      if (!currentMapping) {
        return currentMapping;
      }

      return {
        ...currentMapping,
        saved_mapping: mappingResult.data,
        source_kind: mappingResult.data.source_kind,
      };
    });
    setNotice({
      text: `Mapping saved for ${selectedUpload?.original_filename ?? "the selected upload"}.`,
      tone: "good",
    });

    await refreshUploads(selectedUploadId);
  }

  async function handleTriggerNormalization() {
    if (!selectedUploadId) {
      return;
    }

    if (!mappingIsSaved) {
      setNotice({
        text: "Save the current mapping before starting normalization.",
        tone: "warning",
      });
      return;
    }

    setIsNormalizing(true);
    setNotice(null);

    const normalizationResult =
      await triggerBrowserUploadNormalization(selectedUploadId);

    setIsNormalizing(false);

    if (!normalizationResult.data) {
      setNotice({
        text: normalizationResult.error,
        tone: "danger",
      });
      return;
    }

    setUploads((currentUploads) =>
      upsertUpload(currentUploads, normalizationResult.data),
    );
    setNotice({
      text: `Normalization queued for ${normalizationResult.data.original_filename}.`,
      tone: "warning",
    });

    await refreshUploads(selectedUploadId);
  }

  return (
    <>
      <section className="metric-grid" aria-label="Upload metrics">
        <MetricCard
          detail={
            uploadsError
              ? uploadsError
              : "Tracked files currently registered with the backend."
          }
          label="Registered files"
          tone="accent"
          value={formatNumber(uploads.length)}
        />
        <MetricCard
          detail="Files mapped and ready for a normalization run."
          label="Ready to normalize"
          tone="good"
          value={formatNumber(statusCounts.mapped ?? 0)}
        />
        <MetricCard
          detail="Files that completed normalization, including partial-error runs."
          label="Completed"
          value={formatNumber(completedCount)}
        />
        <MetricCard
          detail="Queued, running, or failed normalization jobs needing attention."
          label="Watchlist"
          tone="warning"
          value={formatNumber(
            (statusCounts.normalization_queued ?? 0) +
              (statusCounts.normalizing ?? 0) +
              (statusCounts.normalization_failed ?? 0),
          )}
        />
      </section>

      {notice ? (
        <div className={`inline-notice inline-notice--${notice.tone}`} role="status">
          {notice.text}
        </div>
      ) : null}

      <section className="content-grid content-grid--wide">
        <SectionCard
          className="span-4"
          description="Send a source file into the ingestion lane and immediately inspect how the backend classifies it."
          kicker="Upload"
          title="Source intake"
        >
          <form className="upload-form" onSubmit={handleUploadSubmit}>
            <label className="field-group" htmlFor="upload-file">
              <span className="field-label">Source file</span>
              <input
                accept=".csv,.xlsx"
                className="field-input"
                id="upload-file"
                ref={fileInputRef}
                type="file"
              />
            </label>
            <p className="workflow-note">
              CSV and XLSX uploads are supported. Preview rows and mapping suggestions
              load automatically after submission.
            </p>
            <div className="button-row">
              <button
                className="button button-primary"
                disabled={isUploading}
                type="submit"
              >
                {isUploading ? "Uploading..." : "Upload file"}
              </button>
            </div>
          </form>

          {selectedUpload ? (
            <div className="detail-grid">
              <div className="detail-item">
                <p className="status-label">Selected file</p>
                <p className="detail-value">{selectedUpload.original_filename}</p>
              </div>
              <div className="detail-item">
                <p className="status-label">Status</p>
                <p className="detail-value">
                  <StatusBadge label={formatStatusLabel(selectedUpload.status)} />
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Size</p>
                <p className="detail-value">
                  {formatBytes(selectedUpload.file_size_bytes)}
                </p>
              </div>
              <div className="detail-item">
                <p className="status-label">Source kind</p>
                <p className="detail-value">
                  {formatStatusLabel(
                    selectedSourceKind || selectedUpload.source_kind || selectedUpload.file_type,
                  )}
                </p>
              </div>
            </div>
          ) : (
            <EmptyState
              description="Upload a file to begin preview, mapping, and normalization."
              title="No file selected"
            />
          )}
        </SectionCard>

        <SectionCard
          action={
            <button
              className="button button-secondary"
              disabled={isRefreshingUploads}
              onClick={() => {
                void refreshUploads(selectedUploadId ?? undefined);
              }}
              type="button"
            >
              {isRefreshingUploads ? "Refreshing..." : "Refresh"}
            </button>
          }
          className="span-8"
          description="Review the latest upload statuses, then pick a file to inspect or continue through mapping and normalization."
          kicker="Queue"
          title="Tracked uploads"
        >
          {uploadsError ? (
            <EmptyState
              description={uploadsError}
              title="Uploads could not be loaded."
              tone="danger"
            />
          ) : uploads.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Rows normalized</th>
                    <th>Errors</th>
                    <th>Uploaded</th>
                    <th>Workflow</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((upload) => (
                    <tr
                      className={upload.id === selectedUploadId ? "is-selected" : undefined}
                      key={upload.id}
                    >
                      <td>
                        <button
                          className="table-link-button"
                          onClick={() => {
                            setSelectedUploadId(upload.id);
                          }}
                          type="button"
                        >
                          <span className="table-link-title">
                            {upload.original_filename}
                          </span>
                          <span className="table-note mono">{upload.id}</span>
                        </button>
                      </td>
                      <td>
                        {formatStatusLabel(upload.source_kind || upload.file_type)}
                      </td>
                      <td>
                        <StatusBadge label={formatStatusLabel(upload.status)} />
                      </td>
                      <td>{formatNumber(upload.normalized_row_count)}</td>
                      <td>{formatNumber(upload.normalization_error_count)}</td>
                      <td>{formatWorkflowDateTime(upload.uploaded_at)}</td>
                      <td className="is-action">
                        <button
                          className="table-action-button"
                          onClick={() => {
                            setSelectedUploadId(upload.id);
                          }}
                          type="button"
                        >
                          {upload.id === selectedUploadId ? "Reviewing" : "Review"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="No uploads are registered yet. Use the intake panel to send the first file through the workflow."
              title="No uploads yet"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-12"
          description="Preview rows let the operator confirm headers and sample values before accepting or editing the schema mapping."
          kicker="Preview"
          title="Preview rows"
        >
          {selectionError ? (
            <EmptyState
              description={selectionError}
              title="Preview details could not be loaded."
              tone="danger"
            />
          ) : !selectedUpload ? (
            <EmptyState
              description="Pick an upload from the queue to review the parsed rows."
              title="No upload selected"
            />
          ) : isLoadingSelection && !selectedUploadPreview ? (
            <div className="loading-preview">
              <div className="loading-line" />
              <div className="loading-line" />
              <div className="loading-line" />
            </div>
          ) : selectedUploadPreview?.columns.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {selectedUploadPreview.columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {selectedUploadPreview.rows.map((row, rowIndex) => (
                    <tr key={`${selectedUploadPreview.upload_id}-${rowIndex}`}>
                      {selectedUploadPreview.columns.map((column) => (
                        <td key={`${rowIndex}-${column}`}>{row[column] || "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              description="The selected upload did not yield any previewable rows."
              title="No preview rows available"
            />
          )}
        </SectionCard>

        <SectionCard
          className="span-8"
          description="Review the suggested matches, edit the canonical field assignments, and save the mapping that normalization will use."
          kicker="Mapping"
          title="Schema mapping"
        >
          {!selectedUpload || !selectedUploadPreview || !selectedUploadMapping ? (
            <EmptyState
              description="Select an upload to review suggested mappings and edit field assignments."
              title="Mapping is waiting on a selected upload"
            />
          ) : (
            <div className="page-stack">
              <div className="mapping-toolbar">
                <label className="field-group" htmlFor="source-kind">
                  <span className="field-label">Source kind</span>
                  <select
                    className="field-select"
                    disabled={isLoadingSelection || isSavingMapping}
                    id="source-kind"
                    onChange={handleSourceKindChange}
                    value={selectedSourceKind}
                  >
                    <option value="">Choose source kind</option>
                    {selectedUploadPreview.supported_source_kinds.map((sourceKind) => (
                      <option key={sourceKind} value={sourceKind}>
                        {formatStatusLabel(sourceKind)}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="workflow-summary">
                  <StatusBadge
                    label={mappingIsSaved ? "Mapping saved" : "Mapping not saved"}
                    tone={mappingIsSaved ? "good" : "warning"}
                  />
                  {selectedUploadPreview.inferred_source_kind ? (
                    <span className="chip">
                      Inferred:{" "}
                      {formatStatusLabel(selectedUploadPreview.inferred_source_kind)}
                    </span>
                  ) : null}
                </div>
              </div>

              {missingRequiredFields.length ? (
                <div className="inline-notice inline-notice--warning">
                  Missing required fields:{" "}
                  {missingRequiredFields
                    .map((field) => field.label)
                    .join(", ")}
                </div>
              ) : null}

              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Source column</th>
                      <th>Sample value</th>
                      <th>Suggested field</th>
                      <th>Mapping</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedUploadPreview.columns.map((column) => {
                      const suggestion = selectedUploadMapping.suggested_mappings.find(
                        (item) => item.source_column === column,
                      );
                      const assignedField = mappingDraft[column] ?? "";
                      const usedFields = new Set(
                        Object.entries(mappingDraft)
                          .filter(([sourceColumn, value]) => {
                            return sourceColumn !== column && Boolean(value);
                          })
                          .map(([, value]) => value),
                      );

                      return (
                        <tr key={column}>
                          <td>
                            <strong>{column}</strong>
                          </td>
                          <td>{selectedUploadPreview.rows[0]?.[column] || "—"}</td>
                          <td>
                            {suggestion ? (
                              <>
                                <strong>
                                  {formatStatusLabel(suggestion.canonical_field)}
                                </strong>
                                <span className="table-note">
                                  {formatPercent(suggestion.confidence)} confidence ·{" "}
                                  {suggestion.reason}
                                </span>
                              </>
                            ) : (
                              <span className="table-note">
                                No automatic suggestion
                              </span>
                            )}
                          </td>
                          <td>
                            <select
                              className="field-select field-select--compact"
                              disabled={
                                isLoadingSelection ||
                                isSavingMapping ||
                                !selectedSourceKind
                              }
                              onChange={(event) => {
                                const nextValue = event.target.value;

                                setMappingDraft((currentDraft) => ({
                                  ...currentDraft,
                                  [column]: nextValue,
                                }));
                              }}
                              value={assignedField}
                            >
                              <option value="">Not mapped</option>
                              {selectedUploadMapping.canonical_fields.map((field) => (
                                <option
                                  disabled={
                                    field.name !== assignedField &&
                                    usedFields.has(field.name)
                                  }
                                  key={field.name}
                                  value={field.name}
                                >
                                  {field.label}
                                  {field.required ? " *" : ""}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="button-row">
                <button
                  className="button button-primary"
                  disabled={
                    isSavingMapping ||
                    isLoadingSelection ||
                    !selectedSourceKind
                  }
                  onClick={() => {
                    void handleSaveMapping();
                  }}
                  type="button"
                >
                  {isSavingMapping ? "Saving..." : "Save mapping"}
                </button>
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard
          className="span-4"
          description="Start normalization after saving a mapping, then watch the upload status update as the backend processes the file."
          kicker="Normalization"
          title="Workflow control"
        >
          {selectedUpload ? (
            <div className="stack-list">
              <div className="list-row">
                <div className="list-row-main">
                  <p className="list-row-title">Current status</p>
                  <p className="list-row-detail">
                    {selectedUpload.last_error ?? "No backend error reported."}
                  </p>
                </div>
                <StatusBadge label={formatStatusLabel(selectedUpload.status)} />
              </div>
              <div className="list-row">
                <div className="list-row-main">
                  <p className="list-row-title">Normalized rows</p>
                  <p className="list-row-detail">
                    Last started{" "}
                    {formatWorkflowDateTime(selectedUpload.normalization_started_at)}
                  </p>
                </div>
                <p className="list-row-value">
                  {formatNumber(selectedUpload.normalized_row_count)}
                </p>
              </div>
              <div className="list-row">
                <div className="list-row-main">
                  <p className="list-row-title">Normalization errors</p>
                  <p className="list-row-detail">
                    Completed{" "}
                    {formatWorkflowDateTime(selectedUpload.normalization_completed_at)}
                  </p>
                </div>
                <p className="list-row-value">
                  {formatNumber(selectedUpload.normalization_error_count)}
                </p>
              </div>
              <div className="button-row">
                <button
                  className="button button-primary"
                  disabled={
                    isNormalizing ||
                    isSavingMapping ||
                    !mappingIsSaved ||
                    missingRequiredFields.length > 0 ||
                    selectedUpload.status === "normalized" ||
                    selectedUpload.status === "normalized_with_errors" ||
                    shouldPollSelectedUpload
                  }
                  onClick={() => {
                    void handleTriggerNormalization();
                  }}
                  type="button"
                >
                  {isNormalizing
                    ? "Starting..."
                    : shouldPollSelectedUpload
                      ? "Normalization running..."
                      : "Start normalization"}
                </button>
              </div>
              {!mappingIsSaved ? (
                <p className="workflow-note">
                  Save the mapping before normalization can begin.
                </p>
              ) : null}
            </div>
          ) : (
            <EmptyState
              description="Choose an upload to manage normalization from this panel."
              title="Normalization is waiting on a selected upload"
            />
          )}
        </SectionCard>
      </section>
    </>
  );
}
