from typing import Literal
from pydantic import BaseModel


class ApplicationData(BaseModel):
    application_id: str | None = None
    ttb_id: str | None = None
    brand_name: str
    fanciful_name: str | None = None
    class_type: str
    alcohol_content: str
    net_contents: str
    producer_name: str | None = None
    producer_address: str | None = None
    country_of_origin: str | None = None
    importer_name: str | None = None
    importer_address: str | None = None
    beverage_type: Literal["beer", "wine", "distilled_spirits"]
    has_sulfites_declaration: bool = False
    source_of_product: Literal["domestic", "imported"] | None = None


class BoundingBox(BaseModel):
    panel: str
    x: float
    y: float
    width: float
    height: float


class FieldComparisonResult(BaseModel):
    field_name: str
    declared_value: str | None = None
    extracted_value: str | None = None
    status: Literal["match", "content_mismatch", "field_missing", "extraction_uncertain"]
    confidence: float
    match_strategy: str
    bounding_box: BoundingBox | None = None
    extraction_confidence: Literal["high", "medium", "low"] | None = None
    confidence_reason: str | None = None
    reviewed: bool = False


class ReviewSummary(BaseModel):
    total_fields: int
    fields_needing_review: int
    fields_reviewed: int
    flagged_field_names: list[str]


class ComplianceIssueResponse(BaseModel):
    field_name: str
    severity: str  # "fail" or "needs_review"
    message: str


class ProcessingStats(BaseModel):
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    extraction_time_ms: int = 0
    total_time_ms: int = 0


class VerificationResult(BaseModel):
    session_id: str
    status: Literal["pending", "pass", "needs_review", "fail"]
    overall_confidence: float
    beverage_type: str
    fields: list[FieldComparisonResult]
    annotated_images: dict[str, str]
    created_at: str
    review_summary: ReviewSummary | None = None
    compliance_issues: list[ComplianceIssueResponse] = []
    processing_stats: ProcessingStats | None = None


class OverrideRequest(BaseModel):
    override_status: Literal["match", "content_mismatch", "field_missing"]
    note: str | None = None


class DecisionRequest(BaseModel):
    decision: Literal["confirmed", "overridden"]
    notes: str | None = None


class FeedbackRequest(BaseModel):
    ai_correct: bool
    field_name: str | None = None
    note: str | None = None


class BatchStatus(BaseModel):
    batch_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    total_items: int
    completed_items: int
    failed_items: int
    created_at: str


class BatchSessionItem(BaseModel):
    session_id: str
    brand_name: str | None = None
    beverage_type: str
    status: str
    overall_confidence: float | None = None
    created_at: str
    processing_stats: ProcessingStats | None = None


class BatchSkippedItem(BaseModel):
    filename: str
    reason: str


class BatchResponse(BaseModel):
    batch: BatchStatus
    items: list[BatchSessionItem]
    skipped_items: list[BatchSkippedItem] = []


class HistoryItem(BaseModel):
    session_id: str
    application_id: str | None = None
    brand_name: str | None = None
    beverage_type: str
    status: str
    overall_confidence: float | None = None
    agent_decision: str | None = None
    created_at: str


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    page: int
    per_page: int
