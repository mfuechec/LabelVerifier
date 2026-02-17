import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.db.setup import get_db
from app.models.schemas import (
    ApplicationData,
    ComplianceIssueResponse,
    FieldComparisonResult,
    ProcessingStats,
    VerificationResult,
    BoundingBox,
    ReviewSummary,
)
from app.services.extraction import BaseExtractor, GroqExtractor, AnthropicExtractor, ExtractionResult, LLMCallStats
from app.services.ttb_classes import is_administrative_class_type
from app.services.pdf_parser import COLAParseResult

IMAGES_BASE_DIR = "data/images"
from app.services.comparison import ComparisonService, ConfidenceScorer
from app.services.compliance import ComplianceChecker
from app.services.merger import ImageMerger
from app.services.image_preprocessor import preprocess_image
from app.services.cost import calculate_cost
from app.services.text_matcher import TextMatcher

import logging

logger = logging.getLogger(__name__)


class VerificationOrchestrator:
    def __init__(self, db_path: str = "data/labelverify.db"):
        self.db_path = db_path
        self.extraction_service: BaseExtractor = self._create_extractor()
        self.comparison_service = ComparisonService()
        self.compliance_checker = ComplianceChecker()
        self.merger = ImageMerger()
        self.scorer = ConfidenceScorer()
        self.text_matcher = TextMatcher()

    @staticmethod
    def _create_extractor() -> BaseExtractor:
        if settings.llm_provider == "anthropic":
            return AnthropicExtractor(
                api_key=settings.anthropic_api_key,
                model=settings.llm_model,
                reextract_model=settings.reextract_model,
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
        t_start = time.monotonic()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        all_llm_stats: list[LLMCallStats] = []

        # 0. Save uploaded images to disk
        annotated_images = {}
        img_dir = Path(IMAGES_BASE_DIR) / session_id
        img_dir.mkdir(parents=True, exist_ok=True)
        for img_bytes, panel in zip(images, panels):
            img_path = img_dir / f"{panel}.jpg"
            img_path.write_bytes(img_bytes)
            annotated_images[panel] = f"/api/v1/images/{session_id}/{panel}"

        # 1. Preprocess images
        processed_images = [preprocess_image(img) for img in images]

        is_admin, _ = is_administrative_class_type(application_data.class_type)
        is_anthropic = isinstance(self.extraction_service, AnthropicExtractor)

        if is_anthropic:
            return await self._verify_transcription_pipeline(
                processed_images, panels, application_data,
                session_id, now, all_llm_stats, annotated_images,
                is_admin, batch_id, t_start,
            )
        else:
            # Groq / legacy: use old extraction pipeline
            return await self._verify_legacy_pipeline(
                processed_images, panels, application_data,
                session_id, now, all_llm_stats, annotated_images,
                batch_id, t_start,
            )

    async def _verify_transcription_pipeline(
        self,
        processed_images: list[bytes],
        panels: list[str],
        application_data: ApplicationData,
        session_id: str,
        now: str,
        all_llm_stats: list[LLMCallStats],
        annotated_images: dict,
        is_admin: bool,
        batch_id: str | None,
        t_start: float,
    ) -> VerificationResult:
        """New pipeline: transcribe all text, then search for declared values."""

        # 2. Transcribe each image in parallel (+ specialty extraction for admin codes)
        all_tasks: dict[str, any] = {}
        for i, (img, panel) in enumerate(zip(processed_images, panels)):
            all_tasks[f"transcribe_{i}"] = self.extraction_service.transcribe_label(img, panel)

        if is_admin:
            front_idx = next((i for i, p in enumerate(panels) if p == "front"), 0)
            all_tasks["specialty"] = self.extraction_service.reextract_specialty_class(
                processed_images[front_idx]
            )

        task_keys = list(all_tasks.keys())
        gathered = await asyncio.gather(*all_tasks.values(), return_exceptions=True)
        results_map = dict(zip(task_keys, gathered))

        # 3. Concatenate transcriptions from all panels
        transcriptions = []
        has_error = False
        for i in range(len(processed_images)):
            key = f"transcribe_{i}"
            r = results_map[key]
            if isinstance(r, Exception):
                logger.error("Transcription failed for panel %s: %s", panels[i], r)
                has_error = True
                continue
            text, stats = r
            all_llm_stats.extend(stats)
            transcriptions.append(text)

        label_text = "\n".join(transcriptions)
        has_empty_extraction = not label_text.strip() and not has_error

        if has_empty_extraction:
            logger.warning(
                "No label content detected across %d panel(s) -- possible missing label image",
                len(processed_images),
            )

        # 4. For admin class codes: extract specialty class data
        specialty_class_data = None
        if is_admin and "specialty" in results_map and not isinstance(results_map["specialty"], Exception):
            specialty_data, spec_stats = results_map["specialty"]
            if spec_stats:
                all_llm_stats.append(spec_stats)
            specialty_class_data = specialty_data

        # 5. Run TextMatcher against transcribed text
        comparison_results = self.text_matcher.match_fields(
            label_text, application_data, application_data.beverage_type,
            specialty_class_data=specialty_class_data,
        )

        # 6. Build extracted_fields dict for compliance checker
        # (compliance checker expects a dict of field_name -> value)
        extracted_fields = {}
        for cr in comparison_results:
            extracted_fields[cr.field_name] = cr.extracted_value

        # 7. Run compliance checks
        is_imported = bool(application_data.country_of_origin or application_data.importer_name)
        compliance_issues = self.compliance_checker.check_compliance(
            extracted_fields,
            application_data.beverage_type,
            is_imported=is_imported,
            requires_sulfites=application_data.has_sulfites_declaration,
        )

        # Merge compliance issues into comparison results
        enriched_results = list(comparison_results)
        compliance_responses = []
        existing_field_names = {r.field_name for r in enriched_results}
        for issue in compliance_issues:
            compliance_responses.append(ComplianceIssueResponse(
                field_name=issue.field_name,
                severity=issue.severity,
                message=issue.message,
            ))
            existing = next(
                (r for r in enriched_results if r.field_name == issue.field_name),
                None,
            )
            if existing and existing.status == "field_missing":
                existing.confidence_reason = issue.message
            elif issue.field_name not in existing_field_names:
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

        # 8. Calculate overall score
        overall_confidence, status = self.scorer.calculate(enriched_results)

        if has_error and not label_text.strip():
            status = "needs_review"
            overall_confidence = 0.0

        if has_empty_extraction:
            status = "needs_review"
            enriched_results.append(FieldComparisonResult(
                field_name="_label_image",
                declared_value=None,
                extracted_value=None,
                status="field_missing",
                confidence=0.0,
                match_strategy="compliance",
                confidence_reason="No label content could be extracted. The label image may be missing, blank, or unreadable.",
            ))

        # 9. Aggregate processing stats
        total_time_ms = int((time.monotonic() - t_start) * 1000)
        total_input_tokens = sum(s.input_tokens for s in all_llm_stats)
        total_output_tokens = sum(s.output_tokens for s in all_llm_stats)
        estimated_cost = calculate_cost(
            total_input_tokens,
            total_output_tokens,
            model=settings.llm_model,
        )
        processing_stats = ProcessingStats(
            total_llm_calls=len(all_llm_stats),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            extraction_time_ms=sum(s.elapsed_ms for s in all_llm_stats),
            total_time_ms=total_time_ms,
            estimated_cost_usd=estimated_cost,
        )

        # 10. Persist to DB
        self._persist_session(
            session_id, application_data, enriched_results,
            overall_confidence, status, now, batch_id=batch_id,
            processing_stats=processing_stats,
        )

        # 11. Compute review summary
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
            processing_stats=processing_stats,
        )

    async def _verify_legacy_pipeline(
        self,
        processed_images: list[bytes],
        panels: list[str],
        application_data: ApplicationData,
        session_id: str,
        now: str,
        all_llm_stats: list[LLMCallStats],
        annotated_images: dict,
        batch_id: str | None,
        t_start: float,
    ) -> VerificationResult:
        """Legacy extraction pipeline for non-Anthropic (Groq) extractor."""
        # Single extract_fields call per panel
        all_tasks = {}
        for i, (img, panel) in enumerate(zip(processed_images, panels)):
            all_tasks[f"extract_{i}"] = self.extraction_service.extract_fields(img, panel)

        task_keys = list(all_tasks.keys())
        gathered = await asyncio.gather(*all_tasks.values(), return_exceptions=True)
        results_map = dict(zip(task_keys, gathered))

        extraction_results: list[ExtractionResult] = []
        for i in range(len(processed_images)):
            r = results_map[f"extract_{i}"]
            if isinstance(r, Exception):
                extraction_results.append(ExtractionResult(panel_type="unknown", error=str(r)))
            else:
                extraction_results.append(r)
                all_llm_stats.extend(r.llm_stats)

        has_error = any(r.error for r in extraction_results)

        # Detect empty extraction
        all_fields_empty = True
        for r in extraction_results:
            if r.error:
                continue
            for field_data in r.fields.values():
                if isinstance(field_data, dict) and field_data.get("value") is not None:
                    all_fields_empty = False
                    break
            if not all_fields_empty:
                break
        has_empty_extraction = all_fields_empty and not has_error

        # Merge panels
        extraction_confidences = {}
        if len(extraction_results) == 1:
            merged_fields = {}
            result = extraction_results[0]
            for field_name, field_data in result.fields.items():
                if isinstance(field_data, dict):
                    merged_fields[field_name] = field_data.get("value")
                    ext_conf = field_data.get("extraction_confidence", "high")
                    extraction_confidences[field_name] = ext_conf
        else:
            panel_data = {}
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
                panel_data[result.panel_type] = panel_fields

            merged = self.merger.merge_panels(panel_data)
            merged_fields = {
                fn: fv.value for fn, fv in merged.fields.items()
            }
            extraction_confidences = {
                fn: fv.extraction_confidence for fn, fv in merged.fields.items()
            }

        # Compare against application data
        comparison_results = self.comparison_service.compare_fields(
            merged_fields, application_data, application_data.beverage_type,
            extraction_confidences=extraction_confidences,
        )

        enriched_results = list(comparison_results)

        # Compliance checks
        is_imported = bool(application_data.country_of_origin or application_data.importer_name)
        compliance_issues = self.compliance_checker.check_compliance(
            merged_fields,
            application_data.beverage_type,
            is_imported=is_imported,
            requires_sulfites=application_data.has_sulfites_declaration,
        )

        compliance_responses = []
        existing_field_names = {r.field_name for r in enriched_results}
        for issue in compliance_issues:
            compliance_responses.append(ComplianceIssueResponse(
                field_name=issue.field_name,
                severity=issue.severity,
                message=issue.message,
            ))
            existing = next(
                (r for r in enriched_results if r.field_name == issue.field_name),
                None,
            )
            if existing and existing.status == "field_missing":
                existing.confidence_reason = issue.message
            elif issue.field_name not in existing_field_names:
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

        overall_confidence, status = self.scorer.calculate(enriched_results)

        if has_error and not merged_fields:
            status = "needs_review"
            overall_confidence = 0.0

        if has_empty_extraction:
            status = "needs_review"
            enriched_results.append(FieldComparisonResult(
                field_name="_label_image",
                declared_value=None,
                extracted_value=None,
                status="field_missing",
                confidence=0.0,
                match_strategy="compliance",
                confidence_reason="No label content could be extracted. The label image may be missing, blank, or unreadable.",
            ))

        total_time_ms = int((time.monotonic() - t_start) * 1000)
        total_input_tokens = sum(s.input_tokens for s in all_llm_stats)
        total_output_tokens = sum(s.output_tokens for s in all_llm_stats)
        estimated_cost = calculate_cost(
            total_input_tokens,
            total_output_tokens,
            model=settings.llm_model,
        )
        processing_stats = ProcessingStats(
            total_llm_calls=len(all_llm_stats),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            extraction_time_ms=sum(s.elapsed_ms for s in all_llm_stats),
            total_time_ms=total_time_ms,
            estimated_cost_usd=estimated_cost,
        )

        self._persist_session(
            session_id, application_data, enriched_results,
            overall_confidence, status, now, batch_id=batch_id,
            processing_stats=processing_stats,
        )

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
            processing_stats=processing_stats,
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
        processing_stats: ProcessingStats | None = None,
    ):
        conn = get_db(self.db_path)
        try:
            with conn:
                ps = processing_stats or ProcessingStats()
                conn.execute(
                    """INSERT INTO verification_sessions
                       (id, application_id, beverage_type, status,
                        overall_confidence, batch_id,
                        total_input_tokens, total_output_tokens,
                        total_llm_calls, processing_time_ms, extraction_time_ms,
                        estimated_cost_usd, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, app_data.application_id,
                     app_data.beverage_type, status, confidence, batch_id,
                     ps.total_input_tokens, ps.total_output_tokens,
                     ps.total_llm_calls, ps.total_time_ms, ps.extraction_time_ms,
                     ps.estimated_cost_usd, now, now),
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
