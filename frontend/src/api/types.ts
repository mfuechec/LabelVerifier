export interface BoundingBox {
  panel: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FieldComparisonResult {
  field_name: string;
  declared_value: string | null;
  extracted_value: string | null;
  status: 'match' | 'content_mismatch' | 'field_missing' | 'extraction_uncertain';
  confidence: number;
  match_strategy: string;
  bounding_box: BoundingBox | null;
  extraction_confidence: 'high' | 'medium' | 'low' | null;
  confidence_reason: string | null;
  reviewed: boolean;
}

export interface ReviewSummary {
  total_fields: number;
  fields_needing_review: number;
  fields_reviewed: number;
  flagged_field_names: string[];
}

export interface ComplianceIssueResponse {
  field_name: string;
  severity: string;
  message: string;
}

export interface VerificationResult {
  session_id: string;
  status: 'pending' | 'pass' | 'needs_review' | 'fail';
  overall_confidence: number;
  beverage_type: string;
  fields: FieldComparisonResult[];
  annotated_images: Record<string, string>;
  created_at: string;
  review_summary: ReviewSummary | null;
  compliance_issues: ComplianceIssueResponse[];
}

export interface HistoryItem {
  session_id: string;
  application_id: string | null;
  brand_name: string | null;
  beverage_type: string;
  status: string;
  overall_confidence: number | null;
  agent_decision: string | null;
  created_at: string;
}

export interface HistoryResponse {
  items: HistoryItem[];
  total: number;
  page: number;
  per_page: number;
}

export interface BatchStatus {
  batch_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  total_items: number;
  completed_items: number;
  failed_items: number;
  created_at: string;
}

export interface ProcessingStats {
  total_llm_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  extraction_time_ms: number;
  total_time_ms: number;
}

export interface BatchSessionItem {
  session_id: string;
  brand_name: string | null;
  beverage_type: string;
  status: string;
  overall_confidence: number | null;
  created_at: string;
  processing_stats: ProcessingStats | null;
}

export interface BatchSkippedItem {
  filename: string;
  reason: string;
}

export interface BatchResponse {
  batch: BatchStatus;
  items: BatchSessionItem[];
  skipped_items: BatchSkippedItem[];
}

export interface OverrideRequest {
  override_status: 'match' | 'content_mismatch' | 'field_missing';
  note?: string;
}

export interface DecisionRequest {
  decision: 'confirmed' | 'overridden';
  notes?: string;
}

export interface FeedbackRequest {
  ai_correct: boolean;
  field_name?: string;
  note?: string;
}
