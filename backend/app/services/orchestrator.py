import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.db.repository import VerificationRepository
from app.models.schemas import (
    ApplicationData,
    ComplianceIssueResponse,
    FieldComparisonResult,
    ProcessingStats,
    VerificationResult,
    ReviewSummary,
)
from app.services.extraction import AnthropicExtractor, LLMCallStats
from app.services.ttb_classes import is_administrative_class_type
from app.services.pdf_parser import COLAParseResult
from app.services.comparison import ConfidenceScorer
from app.services.compliance import ComplianceChecker
from app.services.image_preprocessor import preprocess_image
from app.services.cost import calculate_cost
from app.services.text_matcher import TextMatcher

IMAGES_BASE_DIR = "data/images"

logger = logging.getLogger(__name__)


class VerificationOrchestrator:
    def __init__(self, db_path: str = "data/labelverify.db"):
        self.db_path = db_path
        self.repo = VerificationRepository(db_path)
        self.extraction_service = AnthropicExtractor(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            reextract_model=settings.reextract_model,
        )
        self.compliance_checker = ComplianceChecker()
        self.scorer = ConfidenceScorer()
        self.text_matcher = TextMatcher()

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

        # 2. Transcribe images and extract specialty data
        label_text, specialty_class_data, has_error, has_empty = (
            await self._transcribe_images(
                processed_images, panels, is_admin, all_llm_stats,
            )
        )

        # 3. Match fields and run re-extractions
        comparison_results = await self._match_and_reextract(
            label_text, application_data, specialty_class_data,
            processed_images, panels, all_llm_stats,
        )

        # 4. Run compliance checks and merge into results
        enriched_results, compliance_responses = self._check_compliance(
            comparison_results, application_data,
        )

        # 5. Calculate overall score
        overall_confidence, status = self._compute_score(
            enriched_results, has_error, has_empty, label_text,
        )

        # 6. Aggregate processing stats
        processing_stats = self._aggregate_stats(all_llm_stats, t_start)

        # 7. Persist to DB
        self.repo.create_session(
            session_id, application_data, enriched_results,
            overall_confidence, status, now, batch_id=batch_id,
            processing_stats=processing_stats,
        )

        # 8. Build and return result
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

    async def _transcribe_images(
        self,
        processed_images: list[bytes],
        panels: list[str],
        is_admin: bool,
        all_llm_stats: list[LLMCallStats],
    ) -> tuple[str, dict | None, bool, bool]:
        """Transcribe all panels in parallel. Returns (label_text, specialty_data, has_error, has_empty)."""
        all_tasks: dict[str, Any] = {}
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

        # Concatenate transcriptions
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
        has_empty = not label_text.strip() and not has_error

        if has_empty:
            logger.warning(
                "No label content detected across %d panel(s) -- possible missing label image",
                len(processed_images),
            )

        # Extract specialty class data
        specialty_class_data = None
        if is_admin and "specialty" in results_map and not isinstance(results_map["specialty"], Exception):
            specialty_data, spec_stats = results_map["specialty"]
            if spec_stats:
                all_llm_stats.append(spec_stats)
            specialty_class_data = specialty_data

        return label_text, specialty_class_data, has_error, has_empty

    async def _match_and_reextract(
        self,
        label_text: str,
        application_data: ApplicationData,
        specialty_class_data: dict | None,
        processed_images: list[bytes],
        panels: list[str],
        all_llm_stats: list[LLMCallStats],
    ) -> list[FieldComparisonResult]:
        """Match fields via TextMatcher, then run re-extractions for mismatched fields in parallel."""
        comparison_results = self.text_matcher.match_fields(
            label_text, application_data, application_data.beverage_type,
            specialty_class_data=specialty_class_data,
        )

        # Identify fields needing re-extraction
        abv_result = next(
            (r for r in comparison_results if r.field_name == "alcohol_content"), None
        )
        nc_result = next(
            (r for r in comparison_results if r.field_name == "net_contents"), None
        )

        needs_abv_reextract = (
            abv_result
            and abv_result.status in ("content_mismatch", "extraction_uncertain")
        )
        needs_nc_reextract = (
            nc_result
            and nc_result.status in ("content_mismatch", "field_missing")
        )

        # Run re-extractions in parallel
        reextract_tasks = {}
        if needs_abv_reextract:
            back_idx = next((i for i, p in enumerate(panels) if p == "back"), None)
            reextract_idx = back_idx if back_idx is not None else 0
            reextract_tasks["abv"] = self.extraction_service.reextract_abv(
                processed_images[reextract_idx]
            )
        if needs_nc_reextract:
            front_idx = next((i for i, p in enumerate(panels) if p == "front"), 0)
            reextract_tasks["nc"] = self.extraction_service.reextract_net_contents(
                processed_images[front_idx]
            )

        if reextract_tasks:
            keys = list(reextract_tasks.keys())
            results = await asyncio.gather(*reextract_tasks.values(), return_exceptions=True)
            reextract_results = dict(zip(keys, results))

            # Apply ABV re-extraction
            if "abv" in reextract_results and not isinstance(reextract_results["abv"], Exception):
                reextracted_abv, abv_stats = reextract_results["abv"]
                if abv_stats:
                    all_llm_stats.append(abv_stats)
                if reextracted_abv:
                    new_status, new_conf, new_reason, new_found = self.text_matcher.match_abv(
                        application_data.alcohol_content, f"{reextracted_abv}%"
                    )
                    if new_status == "match":
                        abv_result.status = new_status
                        abv_result.confidence = new_conf
                        abv_result.confidence_reason = f"ABV confirmed via re-extraction: {new_reason}"
                        abv_result.extracted_value = new_found

            # Apply net contents re-extraction
            if "nc" in reextract_results and not isinstance(reextract_results["nc"], Exception):
                reextracted_nc, nc_stats = reextract_results["nc"]
                if nc_stats:
                    all_llm_stats.append(nc_stats)
                if reextracted_nc:
                    new_status, new_conf, new_reason, new_found = self.text_matcher.match_net_contents(
                        application_data.net_contents, reextracted_nc
                    )
                    if new_status == "match":
                        nc_result.status = new_status
                        nc_result.confidence = new_conf
                        nc_result.confidence_reason = f"Net contents confirmed via re-extraction: {new_reason}"
                        nc_result.extracted_value = new_found

        return comparison_results

    def _check_compliance(
        self,
        comparison_results: list[FieldComparisonResult],
        application_data: ApplicationData,
    ) -> tuple[list[FieldComparisonResult], list[ComplianceIssueResponse]]:
        """Run compliance checks and merge issues into field results."""
        # Build extracted_fields dict for compliance checker
        extracted_fields = {}
        for cr in comparison_results:
            if cr.status in ("match", "content_mismatch", "extraction_uncertain"):
                extracted_fields[cr.field_name] = cr.extracted_value or cr.declared_value or "PRESENT"
            else:
                extracted_fields[cr.field_name] = None

        is_imported = bool(application_data.country_of_origin or application_data.importer_name)
        compliance_issues = self.compliance_checker.check_compliance(
            extracted_fields,
            application_data.beverage_type,
            is_imported=is_imported,
            requires_sulfites=application_data.has_sulfites_declaration,
        )

        # Filter out country_of_origin issue when COLA didn't declare one
        if not application_data.country_of_origin:
            compliance_issues = [i for i in compliance_issues if i.field_name != "country_of_origin"]

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

        return enriched_results, compliance_responses

    def _compute_score(
        self,
        enriched_results: list[FieldComparisonResult],
        has_error: bool,
        has_empty: bool,
        label_text: str,
    ) -> tuple[float, str]:
        """Calculate overall confidence score and status."""
        overall_confidence, status = self.scorer.calculate(enriched_results)

        if has_error and not label_text.strip():
            status = "needs_review"
            overall_confidence = 0.0

        if has_empty:
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

        return overall_confidence, status

    def _aggregate_stats(
        self,
        all_llm_stats: list[LLMCallStats],
        t_start: float,
    ) -> ProcessingStats:
        """Aggregate LLM call stats into a ProcessingStats summary."""
        total_time_ms = int((time.monotonic() - t_start) * 1000)
        total_input_tokens = sum(s.input_tokens for s in all_llm_stats)
        total_output_tokens = sum(s.output_tokens for s in all_llm_stats)
        estimated_cost = calculate_cost(
            total_input_tokens,
            total_output_tokens,
            model=settings.llm_model,
        )
        return ProcessingStats(
            total_llm_calls=len(all_llm_stats),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            extraction_time_ms=sum(s.elapsed_ms for s in all_llm_stats),
            total_time_ms=total_time_ms,
            estimated_cost_usd=estimated_cost,
        )

