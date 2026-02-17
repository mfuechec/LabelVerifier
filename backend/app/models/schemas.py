from typing import Literal
from pydantic import BaseModel


class ApplicationData(BaseModel):
    application_id: str | None = None
    brand_name: str
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


class VerificationResult(BaseModel):
    session_id: str
    status: Literal["pending", "pass", "needs_review", "fail"]
    overall_confidence: float
    beverage_type: str
    fields: list[FieldComparisonResult]
    annotated_images: dict[str, str]
    created_at: str


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
