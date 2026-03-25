export type NumericValue = number | string;

export type ApiResult<T> =
  | { data: T; error: null; status: number }
  | { data: null; error: string; status: number | null };

export type ApiMeta = {
  cases_url: string;
  db_health_url: string;
  docs_url: string;
  health_url: string;
  issues_url: string;
  name: string;
  service: string;
  uploads_url: string;
};

export type ApiHealth = {
  dependencies: {
    postgres_db: string;
    postgres_host: string;
    redis_host: string;
  };
  environment: string;
  max_upload_size_bytes: number;
  service: string;
  status: string;
  storage_root: string;
};

export type CopilotChatMessage = {
  content: string;
  role: "assistant" | "system" | "user";
};

export type CopilotUsage = {
  completion_tokens: number | null;
  estimated_cost_usd: NumericValue | null;
  prompt_tokens: number | null;
  total_tokens: number | null;
};

export type CopilotReference = {
  detail: string | null;
  id: string;
  kind: string;
  label: string;
};

export type CopilotToolCall = {
  arguments: Record<string, unknown>;
  name: string;
};

export type CopilotChatRequest = {
  messages: CopilotChatMessage[];
};

export type CopilotChatResponse = {
  latency_ms: number;
  message: string;
  model_name: string;
  provider_name: string;
  references: CopilotReference[];
  status: string;
  tool_calls: CopilotToolCall[];
  trace_id: string;
  usage: CopilotUsage | null;
};

export type UploadJob = {
  file_size_bytes: number;
  file_type: string;
  id: string;
  last_error: string | null;
  normalization_completed_at: string | null;
  normalization_error_count: number;
  normalization_started_at: string | null;
  normalization_task_id: string | null;
  normalized_row_count: number;
  original_filename: string;
  source_kind: string | null;
  status: string;
  uploaded_at: string;
};

export type CanonicalField = {
  description: string;
  label: string;
  name: string;
  required: boolean;
};

export type ColumnMapping = {
  source_column: string;
  canonical_field: string;
};

export type ColumnMappingSuggestion = ColumnMapping & {
  confidence: number;
  reason: string;
};

export type UploadPreview = {
  columns: string[];
  inferred_source_kind: string | null;
  preview_row_count: number;
  rows: Array<Record<string, string>>;
  supported_source_kinds: string[];
  upload_id: string;
};

export type UploadMapping = {
  created_at: string;
  id: string;
  mappings: ColumnMapping[];
  source_kind: string;
  updated_at: string;
  upload_job_id: string;
};

export type UploadSuggestedMapping = {
  canonical_fields: CanonicalField[];
  inferred_source_kind: string | null;
  saved_mapping: UploadMapping | null;
  source_kind: string | null;
  suggested_mappings: ColumnMappingSuggestion[];
  upload_id: string;
};

export type UploadMappingWrite = {
  mappings: ColumnMapping[];
  source_kind: string;
};

export type RecoveryIssueFilters = {
  issue_type?: string;
  parcel_invoice_line_id?: string;
  provider_name?: string;
  severity?: string;
  shipment_id?: string;
  status?: string;
  three_pl_invoice_line_id?: string;
};

export type RecoveryIssue = {
  confidence: NumericValue | null;
  detected_at: string;
  estimated_recoverable_amount: NumericValue | null;
  evidence_json: Record<string, unknown>;
  id: string;
  issue_type: string;
  parcel_invoice_line_id: string | null;
  provider_name: string;
  severity: string;
  shipment_id: string | null;
  status: string;
  summary: string;
  three_pl_invoice_line_id: string | null;
};

export type RecoveryIssueTypeMetric = {
  count: number;
  estimated_recoverable_amount: NumericValue;
  issue_type: string;
};

export type RecoveryIssueProviderMetric = {
  count: number;
  estimated_recoverable_amount: NumericValue;
  provider_name: string;
};

export type RecoveryIssueTrendPoint = {
  count: number;
  date: string;
  estimated_recoverable_amount: NumericValue;
};

export type RecoveryIssueDashboard = {
  issues_by_provider: RecoveryIssueProviderMetric[];
  issues_by_type: RecoveryIssueTypeMetric[];
  total_issue_count: number;
  total_recoverable_amount: NumericValue;
  trend: RecoveryIssueTrendPoint[];
};

export type RecoveryIssueDetection = {
  counts_by_issue_type: Record<string, number>;
  created_count: number;
  deleted_duplicate_count: number;
  total_issue_count: number;
  unchanged_count: number;
  updated_count: number;
};

export type RecoveryCaseStatus = "open" | "pending" | "resolved";

export type RecoveryCaseLinkedIssue = {
  detected_at: string;
  estimated_recoverable_amount: NumericValue | null;
  id: string;
  issue_type: string;
  provider_name: string;
  severity: string;
  status: string;
  summary: string;
};

export type RecoveryCaseListItem = {
  created_at: string;
  draft_email: string | null;
  draft_summary: string | null;
  estimated_recoverable_amount: NumericValue;
  id: string;
  issue_count: number;
  issue_ids: string[];
  status: RecoveryCaseStatus;
  title: string;
  updated_at: string;
};

export type RecoveryCase = RecoveryCaseListItem & {
  issues: RecoveryCaseLinkedIssue[];
};

export type RecoveryCaseCreateRequest = {
  issue_ids: string[];
  title?: string;
};

export type RecoveryCaseUpdateRequest = {
  draft_email: string | null;
  draft_summary: string | null;
  status: RecoveryCaseStatus;
  title: string;
};
