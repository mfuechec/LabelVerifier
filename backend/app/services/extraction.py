import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic, RateLimitError as AnthropicRateLimitError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2

# --- Focused extraction prompts (Group A/B/C) ---

IDENTITY_PROMPT = """Extract identity fields from this US alcohol label. Return ONLY JSON (no markdown):
{"brand_name":{"value":null,"conf":"high"},"fanciful_name":{"value":null,"conf":"high"},"class_type":{"value":null,"conf":"high"},"alcohol_content":{"value":null,"conf":"high"},"alcohol_proof":{"value":null,"conf":"high"}}

Rules: Replace null with extracted text or keep null if not found. conf: high/medium/low. Extract EXACTLY as printed.

- brand_name: Most prominent text. NOT fanciful/secondary name. NOT "Product of...", "Made in...", "Produced by..."
- fanciful_name: Secondary/creative name below brand. null if none
- class_type: Beverage classification (e.g. "Vodka", "Red Wine"). MUST check left/right edges for VERTICAL text
- alcohol_content: Full format as printed (e.g. "45% Alc./Vol.")
- alcohol_proof: Only if separately stated (e.g. "90 Proof")"""

REGULATORY_PROMPT = """Extract regulatory fields from this US alcohol label. Return ONLY JSON (no markdown):
{"government_warning":{"value":null,"conf":"high"},"sulfites_declaration":{"value":null,"conf":"high"},"net_contents":{"value":null,"conf":"high"}}

Rules: Replace null with extracted text or keep null if not found. conf: high/medium/low. Extract EXACTLY as printed.

- government_warning: Find "GOVERNMENT WARNING:" block with (1) pregnancy/birth defects and (2) driving/machinery/health. Read EVERY WORD verbatim. Point (2) says "CONSUMPTION OF ALCOHOLIC BEVERAGES". Include prefix + full text.
- sulfites_declaration: "Contains Sulfites" or similar
- net_contents: Volume as printed (e.g. "750mL", "1.0L"). MUST check all 4 corners and vertical edges for tiny text."""

PRODUCER_ORIGIN_PROMPT = """Extract producer and origin fields from this US alcohol label. Return ONLY JSON (no markdown):
{"producer_name":{"value":null,"conf":"high"},"producer_address":{"value":null,"conf":"high"},"country_of_origin":{"value":null,"conf":"high"},"importer_name":{"value":null,"conf":"high"},"importer_address":{"value":null,"conf":"high"}}

Rules: Replace null with extracted text or keep null if not found. conf: high/medium/low. Extract EXACTLY as printed.

- producer_name: Company that produced/distilled/bottled. Near "Produced by", "Bottled by", "Distilled by". ONLY company name, not prefix
- producer_address: City, state/country of producer. NOT "Produced in Germany" -- look for actual city
- country_of_origin: "Product of [country]", "Made in [country]", "Hecho en [country]", wine regions (e.g. "Niederosterreich, Austria")
- importer_name: After "IMPORTED BY" -- small text near bottom/barcode. Company name only, NOT prefix
- importer_address: City and state after importer name (e.g. "New Rochelle, N.Y.")"""


# Focused prompt for specialty class/type re-extraction (fanciful name + composition)
SPECIALTY_CLASS_PROMPT = """You are an expert text reader for US alcohol label compliance. Your ONLY task is to find the product's distinctive/fanciful name and its statement of composition on this label.

For specialty and proprietary spirits, the label will NOT say a standard class like "Vodka" or "Whiskey". Instead it shows:
1. A FANCIFUL/DISTINCTIVE NAME -- the creative product name (e.g. "Fireball", "Jagermeister", "Barenjager")
2. A STATEMENT OF COMPOSITION -- describes what the product is (e.g. "Cinnamon Whisky", "Liqueur", "Honey & Bourbon Liqueur", "Whisky with natural honey flavor")

The fanciful name is usually the most prominent text. The composition statement is often in smaller text nearby, describing the product type or ingredients.

Return ONLY a JSON object (no markdown, no extra text):
{"fanciful_name": {"value": null, "conf": "high"}, "composition_statement": {"value": null, "conf": "high"}}

Rules:
- fanciful_name: The creative/brand product name (NOT the company name, NOT regulatory text)
- composition_statement: The description of what the product is or contains
- Replace null with the extracted string, or keep null if not found
- conf: "high" = clearly readable, "medium" = partially obscured, "low" = barely legible
- Extract EXACTLY as printed -- do NOT correct errors"""


MISSING_FIELDS_PROMPT = """You are an expert text reader for US alcohol labels. Some fields were missed in a prior extraction. Your ONLY job is to find the specific missing fields listed below.

SEARCH STRATEGY -- these fields are often in hard-to-read locations:
- Fine print at the very bottom of the label
- Vertically rotated text along left/right edges
- Tiny text near barcodes or UPC codes
- Text in corners, especially bottom-left and bottom-right
- Text partially obscured by decorative elements

Return ONLY a JSON object with the requested fields (no markdown, no extra text).
Each field: {{"value": "extracted text or null", "conf": "high/medium/low"}}
Extract EXACTLY as printed. Set null only if truly not visible anywhere on the label."""

BRAND_CONFIRM_PROMPT = """You are an expert text reader for US alcohol label compliance. Your ONLY task is to locate the BRAND NAME on this label.

The application declares the brand name as: "{declared_brand}"

Search the ENTIRE label image carefully for this brand name or any close variant. Brand names are typically the most prominent text, but may also appear in smaller regulatory text.

IMPORTANT RULES:
- If you find "{declared_brand}" or a close variant, extract it EXACTLY as printed on the label
- If you cannot find it anywhere, extract whatever text you believe is the actual brand name
- Do NOT just repeat back "{declared_brand}" -- you must find it visually on the label
- Look at ALL text including decorative/stylized text and fine print

Return ONLY a JSON object (no markdown, no extra text):
{{"brand_name": {{"value": null, "conf": "high"}}, "location_description": null}}

Rules:
- brand_name.value: The brand name as printed on the label, or null if not visible
- brand_name.conf: "high" = clearly readable, "medium" = stylized/decorative, "low" = barely legible
- location_description: Where on the label you found it (e.g. "large text at top center")
- Extract EXACTLY as printed -- do NOT correct spelling"""

TRANSCRIPTION_PROMPT = """Transcribe ALL visible text on this alcohol beverage label image.
Include everything: brand names, product descriptions, warnings, volumes, percentages,
company names, addresses, fine print, vertically rotated text along edges, and tiny text
in corners. Preserve the text as printed (do not correct spelling).
Separate distinct text blocks with newlines. Return ONLY the transcribed text."""

NET_CONTENTS_REEXTRACT_PROMPT = """You are an expert text reader for US alcohol labels. Your ONLY task is to find the exact net contents (volume) on this label.
Look carefully at all text on the label, especially fine print, corners, and edges. The net contents is usually printed as a number followed by a unit (e.g. "750 mL", "1 LITER", "12 FL. OZ.", "1.75L").
Return ONLY a JSON object (no markdown, no extra text): {"net_contents": "<volume with unit>"}
If you cannot find the net contents, return: {"net_contents": null}"""

ABV_REEXTRACT_PROMPT = """You are an expert text reader for US alcohol labels. Your ONLY task is to find the exact alcohol by volume (ABV) percentage on this label.
Look carefully at all text on the label, especially fine print, corners, and edges. The ABV is usually printed as a number followed by a percent sign (e.g. "35%", "40% ALC./VOL.").
Return ONLY a JSON object (no markdown, no extra text): {"abv": "<number>"}
If you cannot find the ABV, return: {"abv": null}"""


@dataclass
class LLMCallStats:
    input_tokens: int
    output_tokens: int
    elapsed_ms: int
    call_type: str


@dataclass
class ExtractionResult:
    fields: dict = field(default_factory=dict)
    panel_type: str = ""
    extraction_notes: str = ""
    error: str | None = None
    llm_stats: list[LLMCallStats] = field(default_factory=list)


def _repair_json(text: str) -> dict | None:
    """Attempt to repair truncated or malformed JSON from LLM output."""
    cleaned = text.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif cleaned.startswith("```"):
        # Unclosed code fence (truncated) -- strip the opening fence
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned).strip()

    # Try parsing as-is first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt to close truncated JSON by adding missing braces/brackets
    repaired = cleaned
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")

    # Trim trailing comma or incomplete key/value
    repaired = re.sub(r',\s*$', '', repaired)
    # Trim incomplete string value (trailing unclosed quote)
    repaired = re.sub(r':\s*"[^"]*$', ': null', repaired)
    # Trim incomplete key
    repaired = re.sub(r',\s*"[^"]*$', '', repaired)

    repaired += "]" * max(0, open_brackets) + "}" * max(0, open_braces)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: extract individual field values with regex
    extracted = {}
    # Match "field_name": "value" or "field_name": null
    for match in re.finditer(r'"(\w+)"\s*:\s*(?:"((?:[^"\\]|\\.)*)"|null)', cleaned):
        key, val = match.group(1), match.group(2)
        extracted[key] = val  # val is None if null was matched
    if extracted:
        return extracted

    return None




def _convert_parsed_to_fields(parsed: dict) -> dict:
    """Convert parsed JSON to the expected format with value/bounding_box/extraction_confidence."""
    fields = {}
    for key, value in parsed.items():
        if key in ("fields", "extraction_notes"):
            continue
        if isinstance(value, dict) and "value" in value:
            fields[key] = {
                "value": value["value"],
                "bounding_box": None,
                "extraction_confidence": value.get("conf", "high"),
            }
        else:
            fields[key] = {
                "value": value,
                "bounding_box": None,
                "extraction_confidence": "high",
            }
    return fields


class AnthropicExtractor:
    HAIKU_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929", reextract_model: str | None = None):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.reextract_model = reextract_model or self.HAIKU_MODEL

    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract all fields by running 3 focused calls in parallel and merging."""
        results = await asyncio.gather(
            self.extract_identity(image_bytes, panel_type, mime_type),
            self.extract_regulatory(image_bytes, panel_type, mime_type),
            self.extract_producer_origin(image_bytes, panel_type, mime_type),
        )
        merged = ExtractionResult(panel_type=panel_type)
        for r in results:
            merged.fields.update(r.fields)
            merged.llm_stats.extend(r.llm_stats)
            if r.error and not merged.error:
                merged.error = r.error
        return merged

    async def _call_llm(
        self,
        image_bytes: bytes,
        system_prompt: str,
        user_text: str,
        call_type: str,
        mime_type: str = "image/jpeg",
        max_tokens: int = 300,
        model: str | None = None,
    ) -> tuple[str, LLMCallStats]:
        """Core LLM call with retry on rate limits.

        Returns (response_text, stats). Raises on exhausted retries or errors.
        Uses model param if given, otherwise falls back to self.reextract_model.
        """
        use_model = model or self.reextract_model
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                t0 = time.monotonic()
                response = await self.client.messages.create(
                    model=use_model,
                    max_tokens=max_tokens,
                    temperature=0,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_image,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": user_text,
                                },
                            ],
                        }
                    ],
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                usage = response.usage
                stats = LLMCallStats(
                    input_tokens=getattr(usage, "input_tokens", 0),
                    output_tokens=getattr(usage, "output_tokens", 0),
                    elapsed_ms=elapsed_ms,
                    call_type=call_type,
                )
                logger.info(
                    "Anthropic %s: %d in / %d out tokens, %dms",
                    call_type, stats.input_tokens, stats.output_tokens, stats.elapsed_ms,
                )

                response_text = response.content[0].text
                logger.info("Anthropic %s response: %s", call_type, response_text[:200])
                return response_text, stats

            except AnthropicRateLimitError as e:
                last_error = e
                if attempt >= MAX_RETRIES:
                    break
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "Anthropic rate limited %s (attempt %d/%d), retrying in %.1fs...",
                    call_type, attempt + 1, MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)

        raise last_error

    async def _call_llm_json(
        self,
        image_bytes: bytes,
        system_prompt: str,
        user_text: str,
        call_type: str,
        mime_type: str = "image/jpeg",
        max_tokens: int = 300,
        model: str | None = None,
    ) -> tuple[dict | None, LLMCallStats]:
        """Call LLM and parse JSON response. Returns (parsed_dict_or_None, stats)."""
        text, stats = await self._call_llm(
            image_bytes, system_prompt, user_text, call_type, mime_type, max_tokens,
            model=model,
        )
        parsed = _repair_json(text)
        if parsed is None:
            logger.error("JSON parse error (%s): %s", call_type, text[:200])
        return parsed, stats

    async def _focused_extract(
        self,
        image_bytes: bytes,
        panel_type: str,
        prompt: str,
        call_type: str,
        user_text: str,
        mime_type: str = "image/jpeg",
        max_tokens: int = 300,
    ) -> ExtractionResult:
        """Focused extraction: calls LLM, parses JSON, returns ExtractionResult."""
        try:
            parsed, stats = await self._call_llm_json(
                image_bytes, prompt, user_text, call_type, mime_type, max_tokens,
            )
            if parsed is None:
                return ExtractionResult(fields={}, panel_type=panel_type, llm_stats=[stats])
            fields = _convert_parsed_to_fields(parsed)
            return ExtractionResult(fields=fields, panel_type=panel_type, llm_stats=[stats])
        except AnthropicRateLimitError as e:
            logger.error("Anthropic %s rate limit exhausted (%s): %s", call_type, panel_type, e)
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Rate limited after {MAX_RETRIES + 1} attempts: {e}",
            )
        except Exception as e:
            logger.exception("Anthropic %s failed (%s): %s", call_type, panel_type, e)
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Extraction failed: {e}",
            )

    async def extract_identity(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract identity fields: brand, fanciful name, class/type, ABV, proof."""
        return await self._focused_extract(
            image_bytes, panel_type, IDENTITY_PROMPT,
            "extract_identity", "Extract the identity fields from this label.",
            mime_type, max_tokens=300,
        )

    async def extract_regulatory(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract regulatory fields: government warning, sulfites, net contents."""
        return await self._focused_extract(
            image_bytes, panel_type, REGULATORY_PROMPT,
            "extract_regulatory", "Extract the regulatory fields from this label.",
            mime_type, max_tokens=512,
        )

    async def extract_producer_origin(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract producer/origin fields: producer, address, country, importer."""
        return await self._focused_extract(
            image_bytes, panel_type, PRODUCER_ORIGIN_PROMPT,
            "extract_producer_origin", "Extract the producer and origin fields from this label.",
            mime_type, max_tokens=512,
        )

    async def reextract_missing_fields(
        self,
        image_bytes: bytes,
        missing_fields: list[str],
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Re-extract specific fields that were null after initial extraction.

        Args:
            image_bytes: The label image.
            missing_fields: List of field names to re-extract.
            mime_type: Image MIME type.

        Returns:
            ExtractionResult with only the requested fields populated.
        """
        # Build field-specific guidance for the user message
        field_hints = {
            "government_warning": "Look for 'GOVERNMENT WARNING:' block -- often in small print on back label. Two numbered points about (1) pregnancy and (2) driving.",
            "net_contents": "Volume measurement (e.g. '750mL', '1.0L'). Check all 4 corners and vertical edges.",
            "producer_name": "Company name near 'Produced by', 'Bottled by', 'Distilled by'.",
            "producer_address": "City/state near producer name.",
            "importer_name": "Company name after 'Imported by' -- small text near bottom/barcode.",
            "importer_address": "City/state after importer name.",
        }

        json_template = {f: {"value": None, "conf": "high"} for f in missing_fields}
        field_guidance = "\n".join(
            f"- {f}: {field_hints.get(f, 'Extract as printed.')}"
            for f in missing_fields
        )

        user_text = (
            f"Find these MISSING fields: {', '.join(missing_fields)}\n\n"
            f"Return JSON: {json.dumps(json_template)}\n\n"
            f"Field guidance:\n{field_guidance}"
        )

        return await self._focused_extract(
            image_bytes, "reextract", MISSING_FIELDS_PROMPT,
            "reextract_missing_fields", user_text,
            mime_type, max_tokens=512,
        )

    async def reextract_specialty_class(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> tuple[dict | None, LLMCallStats | None]:
        """Re-extract fanciful name and composition statement for specialty products."""
        try:
            parsed, stats = await self._call_llm_json(
                image_bytes, SPECIALTY_CLASS_PROMPT,
                "Extract the specialty class information from this label.",
                "reextract_specialty_class", mime_type, max_tokens=512,
            )
            if parsed is None:
                return None, stats

            result = {}
            for key in ("fanciful_name", "composition_statement"):
                fld = parsed.get(key)
                if isinstance(fld, dict) and "value" in fld:
                    result[key] = fld["value"]
                elif isinstance(fld, str):
                    result[key] = fld

            return (result if any(result.values()) else None), stats
        except Exception as e:
            logger.exception("Specialty class re-extraction failed: %s", e)
            return None, None

    async def reextract_abv(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> tuple[str | None, LLMCallStats | None]:
        """Re-extract ABV with a focused prompt for small/misread labels."""
        try:
            parsed, stats = await self._call_llm_json(
                image_bytes, ABV_REEXTRACT_PROMPT,
                "What is the exact ABV percentage on this label?",
                "reextract_abv", mime_type, max_tokens=64,
            )
            if parsed is None:
                return None, stats
            abv = parsed.get("abv")
            if abv is not None:
                abv = str(abv).strip().rstrip("%")
            return (abv if abv else None), stats
        except Exception as e:
            logger.exception("ABV re-extraction failed: %s", e)
            return None, None

    async def reextract_net_contents(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> tuple[str | None, LLMCallStats | None]:
        """Re-extract net contents with a focused prompt for misread labels."""
        try:
            parsed, stats = await self._call_llm_json(
                image_bytes, NET_CONTENTS_REEXTRACT_PROMPT,
                "What is the exact net contents (volume) on this label?",
                "reextract_net_contents", mime_type, max_tokens=64,
            )
            if parsed is None:
                return None, stats
            nc = parsed.get("net_contents")
            if nc is not None:
                nc = str(nc).strip()
            return (nc if nc else None), stats
        except Exception as e:
            logger.exception("Net contents re-extraction failed: %s", e)
            return None, None

    async def reextract_brand(
        self,
        image_bytes: bytes,
        declared_brand: str,
        mime_type: str = "image/jpeg",
    ) -> tuple[dict | None, LLMCallStats | None]:
        """Re-extract brand name with a focused prompt using declared brand as hint."""
        try:
            parsed, stats = await self._call_llm_json(
                image_bytes,
                BRAND_CONFIRM_PROMPT.format(declared_brand=declared_brand),
                "Confirm the brand name on this label.",
                "reextract_brand", mime_type, max_tokens=256,
            )
            if parsed is None:
                return None, stats

            bn = parsed.get("brand_name")
            if isinstance(bn, dict) and "value" in bn:
                brand_value = bn["value"]
                conf = bn.get("conf", "high")
            elif isinstance(bn, str):
                brand_value = bn
                conf = "high"
            else:
                return None, stats

            location = parsed.get("location_description")
            return {"brand_name": brand_value, "conf": conf, "location_description": location}, stats
        except Exception as e:
            logger.exception("Brand re-extraction failed: %s", e)
            return None, None

    async def transcribe_label(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> tuple[str, list[LLMCallStats]]:
        """Transcribe all visible text on a label image."""
        try:
            text, stats = await self._call_llm(
                image_bytes, TRANSCRIPTION_PROMPT,
                "Transcribe all text visible on this label.",
                "transcribe_label", mime_type, max_tokens=4000,
                model=self.model,
            )
            return text, [stats]
        except AnthropicRateLimitError as e:
            logger.error("Transcription rate limit exhausted (%s): %s", panel_type, e)
            return "", []
        except Exception as e:
            logger.exception("Transcription failed (%s): %s", panel_type, e)
            return "", []
