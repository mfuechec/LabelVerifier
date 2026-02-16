import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db.setup import get_db
from app.models.schemas import (
    ApplicationData,
    ComplianceIssueResponse,
    FieldComparisonResult,
    VerificationResult,
    BoundingBox,
    ReviewSummary,
)
from app.services.extraction import BaseExtractor, GroqExtractor, AnthropicExtractor, ExtractionResult
from app.services.pdf_parser import COLAParseResult

IMAGES_BASE_DIR = "data/images"
from app.services.comparison import ComparisonService, ConfidenceScorer
from app.services.compliance import ComplianceChecker
from app.services.merger import ImageMerger
from app.services.image_preprocessor import preprocess_image


class VerificationOrchestrator:
    def __init__(self, db_path: str = "data/labelverify.db"):
        self.db_path = db_path
        self.extraction_service: BaseExtractor = self._create_extractor()
        self.comparison_service = ComparisonService()
        self.compliance_checker = ComplianceChecker()
        self.merger = ImageMerger()
        self.scorer = ConfidenceScorer()

    @staticmethod
    def _create_extractor() -> BaseExtractor:
        if settings.llm_provider == "anthropic":
            return AnthropicExtractor(
                api_key=settings.anthropic_api_key,
                model=settings.llm_model,
            )
        return GroqExtractor(
            api_key=settings.groq_api_key,
            model=settings.llm_model,
        )

    async def verify_from_cola(
        self,
        parse_result: COLAParseResult,
        batch_id: str | None = None,
    ) -> VerificationResult:
        """Verify from a parsed COLA PDF result."""
        images = [li.image_bytes for li in parse_result.label_images]
        panels = [li.panel_type for li in parse_result.label_images]
        return await self.verify_single(
            images, panels, parse_result.application_data, batch_id=batch_id,
        )

    async def verify_single(
        self,
        images: list[bytes],
        panels: list[str],
        application_data: ApplicationData,
        batch_id: str | None = None,
    ) -> VerificationResult:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # 0. Save uploaded images to disk
        annotated_images = {}
        img_dir = Path(IMAGES_BASE_DIR) / session_id
        img_dir.mkdir(parents=True, exist_ok=True)
        for img_bytes, panel in zip(images, panels):
            img_path = img_dir / f"{panel}.jpg"
            img_path.write_bytes(img_bytes)
            annotated_images[panel] = f"/api/v1/images/{session_id}/{panel}"

        # 1. Preprocess images (upscale small images, sharpen for text readability)
        processed_images = [preprocess_image(img) for img in images]

        # Extract fields from each panel (parallel)
        extraction_tasks = [
            self.extraction_service.extract_fields(img, panel)
            for img, panel in zip(processed_images, panels)
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
                    extraction_confidence=cr.extraction_confidence,
                    confidence_reason=cr.confidence_reason,
                )
            )

        # 6. Run compliance checks (independent of application data)
        is_imported = bool(application_data.country_of_origin or application_data.importer_name)
        compliance_issues = self.compliance_checker.check_compliance(
            merged_fields,
            application_data.beverage_type,
            is_imported=is_imported,
            requires_sulfites=application_data.has_sulfites_declaration,
        )

        # Merge compliance issues into comparison results
        compliance_responses = []
        existing_field_names = {r.field_name for r in enriched_results}
        for issue in compliance_issues:
            compliance_responses.append(ComplianceIssueResponse(
                field_name=issue.field_name,
                severity=issue.severity,
                message=issue.message,
            ))
            # Check if there's already a result for this field
            existing = next(
                (r for r in enriched_results if r.field_name == issue.field_name),
                None,
            )
            if existing and existing.status == "field_missing":
                # Enrich existing field_missing result with compliance message
                existing.confidence_reason = issue.message
            elif issue.field_name not in existing_field_names:
                # Add new result for fields not in comparison (skipped by app data)
                status_val = (
                    "extraction_uncertain" if issue.severity == "needs_review"
                    else "field_missing"
                )
                enriched_results.append(FieldComparisonResult(
                    field_name=issue.field_name,
                    declared_value=None,
                    extracted_value=None,
                    status=status_val,
                    confidence=0.0,
                    match_strategy="compliance",
                    confidence_reason=issue.message,
                ))
                existing_field_names.add(issue.field_name)

        # 7. Calculate overall score
        overall_confidence, status = self.scorer.calculate(enriched_results)

        if has_error and not merged_fields:
            status = "needs_review"
            overall_confidence = 0.0

        # 8. Persist to DB
        self._persist_session(
            session_id, application_data, enriched_results,
            overall_confidence, status, now, batch_id=batch_id,
        )

        # 9. Compute review summary
        flagged = [f for f in enriched_results if f.status == "extraction_uncertain"]
        review_summary = ReviewSummary(
            total_fields=len(enriched_results),
            fields_needing_review=len(flagged),
            fields_reviewed=0,
            flagged_field_names=[f.field_name for f in flagged],
        )

        return VerificationResult(
            session_id=session_id,
            status=status,
            overall_confidence=overall_confidence,
            beverage_type=application_data.beverage_type,
            fields=enriched_results,
            annotated_images=annotated_images,
            created_at=now,
            review_summary=review_summary,
            compliance_issues=compliance_responses,
        )

    def _persist_session(
        self,
        session_id: str,
        app_data: ApplicationData,
        fields: list[FieldComparisonResult],
        confidence: float,
        status: str,
        now: str,
        batch_id: str | None = None,
    ):
        conn = get_db(self.db_path)
        try:
            with conn:
                conn.execute(
                    """INSERT INTO verification_sessions
                       (id, application_id, beverage_type, status,
                        overall_confidence, batch_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, app_data.application_id,
                     app_data.beverage_type, status, confidence, batch_id, now, now),
                )

                app_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO applications
                       (id, session_id, brand_name, class_type, alcohol_content,
                        net_contents, producer_name, producer_address,
                        country_of_origin, importer_name, importer_address,
                        has_sulfites_declaration, raw_json,
                        fanciful_name, ttb_id, source_of_product)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (app_id, session_id, app_data.brand_name, app_data.class_type,
                     app_data.alcohol_content, app_data.net_contents,
                     app_data.producer_name, app_data.producer_address,
                     app_data.country_of_origin, app_data.importer_name,
                     app_data.importer_address,
                     1 if app_data.has_sulfites_declaration else 0,
                     app_data.model_dump_json(),
                     app_data.fanciful_name, app_data.ttb_id,
                     app_data.source_of_product),
                )

                for field in fields:
                    cr_id = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO comparison_results
                           (id, session_id, field_name, declared_value,
                            extracted_value, match_strategy, status, confidence,
                            extraction_confidence, confidence_reason)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (cr_id, session_id, field.field_name,
                         field.declared_value, field.extracted_value,
                         field.match_strategy, field.status, field.confidence,
                         field.extraction_confidence, field.confidence_reason),
                    )
        finally:
            conn.close()
