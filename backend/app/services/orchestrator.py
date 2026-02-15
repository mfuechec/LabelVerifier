import asyncio
import json
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.db.setup import get_db, create_tables
from app.models.schemas import (
    ApplicationData,
    FieldComparisonResult,
    VerificationResult,
    BoundingBox,
)
from app.services.extraction import ExtractionService, ExtractionResult
from app.services.comparison import ComparisonService, ConfidenceScorer
from app.services.compliance import ComplianceChecker
from app.services.merger import ImageMerger
from app.services.annotation import AnnotationService


class VerificationOrchestrator:
    def __init__(self, db_path: str = "data/labelverify.db"):
        self.db_path = db_path
        self.extraction_service = ExtractionService(api_key=settings.groq_api_key, model=settings.llm_model)
        self.comparison_service = ComparisonService()
        self.compliance_checker = ComplianceChecker()
        self.merger = ImageMerger()
        self.annotation_service = AnnotationService()
        self.scorer = ConfidenceScorer()

    async def verify_single(
        self,
        images: list[bytes],
        panels: list[str],
        application_data: ApplicationData,
    ) -> VerificationResult:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # 1. Extract fields from each panel (parallel)
        extraction_tasks = [
            self.extraction_service.extract_fields(img, panel)
            for img, panel in zip(images, panels)
        ]
        extraction_results: list[ExtractionResult] = await asyncio.gather(
            *extraction_tasks, return_exceptions=True
        )

        # Handle any extraction errors
        valid_results: list[ExtractionResult] = []
        for r in extraction_results:
            if isinstance(r, Exception):
                valid_results.append(ExtractionResult(panel_type="unknown", error=str(r)))
            else:
                valid_results.append(r)
        extraction_results = valid_results

        # 2. Check for extraction errors
        has_error = any(r.error for r in extraction_results)

        # 3. Merge panels
        extraction_confidences = {}
        if len(extraction_results) == 1:
            merged_fields = {}
            result = extraction_results[0]
            for field_name, field_data in result.fields.items():
                if isinstance(field_data, dict):
                    merged_fields[field_name] = field_data.get("value")
                    ext_conf = field_data.get("extraction_confidence", "high")
                    extraction_confidences[field_name] = ext_conf
            panel_bboxes = {
                fn: {
                    "panel": result.panel_type,
                    **(fd.get("bounding_box") or {})
                }
                for fn, fd in result.fields.items()
                if isinstance(fd, dict) and fd.get("bounding_box")
            }
        else:
            panel_data = {}
            panel_bboxes = {}
            for result in extraction_results:
                panel_fields = {}
                for field_name, field_data in result.fields.items():
                    if isinstance(field_data, dict):
                        panel_fields[field_name] = {
                            "value": field_data.get("value"),
                            "confidence": 90.0,
                            "bounding_box": field_data.get("bounding_box"),
                            "extraction_confidence": field_data.get("extraction_confidence", "high"),
                        }
                        if field_data.get("bounding_box"):
                            panel_bboxes[field_name] = {
                                "panel": result.panel_type,
                                **field_data["bounding_box"],
                            }
                panel_data[result.panel_type] = panel_fields

            merged = self.merger.merge_panels(panel_data)
            merged_fields = {
                fn: fv.value for fn, fv in merged.fields.items()
            }
            extraction_confidences = {
                fn: fv.extraction_confidence for fn, fv in merged.fields.items()
            }

        # 4. Compare against application data
        comparison_results = self.comparison_service.compare_fields(
            merged_fields, application_data, application_data.beverage_type,
            extraction_confidences=extraction_confidences,
        )

        # 5. Add bounding boxes to comparison results
        enriched_results = []
        for cr in comparison_results:
            bbox = None
            if cr.field_name in panel_bboxes:
                bb = panel_bboxes[cr.field_name]
                if "x" in bb:
                    bbox = BoundingBox(
                        panel=bb.get("panel", "front"),
                        x=bb["x"],
                        y=bb["y"],
                        width=bb["width"],
                        height=bb["height"],
                    )
            enriched_results.append(
                FieldComparisonResult(
                    field_name=cr.field_name,
                    declared_value=cr.declared_value,
                    extracted_value=cr.extracted_value,
                    status=cr.status,
                    confidence=cr.confidence,
                    match_strategy=cr.match_strategy,
                    bounding_box=bbox,
                )
            )

        # 6. Calculate overall score
        overall_confidence, status = self.scorer.calculate(enriched_results)

        if has_error and not merged_fields:
            status = "needs_review"
            overall_confidence = 0.0

        # 7. Persist to DB
        self._persist_session(
            session_id, application_data, enriched_results,
            overall_confidence, status, now,
        )

        return VerificationResult(
            session_id=session_id,
            status=status,
            overall_confidence=overall_confidence,
            beverage_type=application_data.beverage_type,
            fields=enriched_results,
            annotated_images={},
            created_at=now,
        )

    def _persist_session(
        self,
        session_id: str,
        app_data: ApplicationData,
        fields: list[FieldComparisonResult],
        confidence: float,
        status: str,
        now: str,
    ):
        conn = get_db(self.db_path)
        try:
            with conn:
                conn.execute(
                    """INSERT INTO verification_sessions
                       (id, application_id, beverage_type, status,
                        overall_confidence, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, app_data.application_id,
                     app_data.beverage_type, status, confidence, now, now),
                )

                app_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO applications
                       (id, session_id, brand_name, class_type, alcohol_content,
                        net_contents, producer_name, producer_address,
                        country_of_origin, importer_name, importer_address,
                        has_sulfites_declaration, raw_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (app_id, session_id, app_data.brand_name, app_data.class_type,
                     app_data.alcohol_content, app_data.net_contents,
                     app_data.producer_name, app_data.producer_address,
                     app_data.country_of_origin, app_data.importer_name,
                     app_data.importer_address,
                     1 if app_data.has_sulfites_declaration else 0,
                     app_data.model_dump_json()),
                )

                for field in fields:
                    cr_id = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO comparison_results
                           (id, session_id, field_name, declared_value,
                            extracted_value, match_strategy, status, confidence)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (cr_id, session_id, field.field_name,
                         field.declared_value, field.extracted_value,
                         field.match_strategy, field.status, field.confidence),
                    )
        finally:
            conn.close()
