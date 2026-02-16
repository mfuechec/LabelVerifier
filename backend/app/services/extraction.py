import abc
import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic
from groq import AsyncGroq, RateLimitError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2

# Single combined prompt: all fields + government warning in one call
EXTRACTION_PROMPT = """You are an alcohol beverage label analysis system for the US TTB. Extract ALL compliance-relevant fields from this label image.

Return ONLY a JSON object exactly like this (no markdown, no extra text):
{"brand_name":{"value":null,"conf":"high"},"class_type":{"value":null,"conf":"high"},"alcohol_content":{"value":null,"conf":"high"},"alcohol_proof":{"value":null,"conf":"high"},"net_contents":{"value":null,"conf":"high"},"producer_name":{"value":null,"conf":"high"},"producer_address":{"value":null,"conf":"high"},"country_of_origin":{"value":null,"conf":"high"},"importer_name":{"value":null,"conf":"high"},"importer_address":{"value":null,"conf":"high"},"government_warning":{"value":null,"conf":"high"},"sulfites_declaration":{"value":null,"conf":"high"}}

Rules:
- Replace null with the extracted string value, or keep null if not found on the label
- If a field is NOT clearly visible on the label, set value to null. Do NOT guess or fabricate text.
- conf: "high" = clearly readable, "medium" = stylized/decorative/partially obscured, "low" = barely legible or guessing
- Do NOT correct spelling, grammar, or formatting errors -- extract EXACTLY as printed on the label

Field-specific guidance:
- brand_name: The product brand name, usually the most prominent text on the label. Do NOT confuse regulatory text like "Hecho en Mexico", "Made in [country]", "Product of [country]", or "Produced and Bottled by..." with the brand name -- those belong in country_of_origin or producer fields
- class_type: The beverage classification (e.g. "Straight Bourbon Whiskey", "Vodka", "Red Wine"). Include qualifiers like "flavored" or geographic terms, but separate finishing/aging statements like "Finished in Port Wine Barrels" from the base class designation
- alcohol_content: Include the full format as printed (e.g. "45% Alc./Vol.", "35% ALC. BY VOL.")
- alcohol_proof: Extract only if separately stated (e.g. "90 Proof")
- net_contents: The volume measurement as printed (e.g. "750mL", "50ML", "25.4 FL OZ"). Read the number carefully
- producer_name: The company that produced/distilled/bottled the product. Look near phrases like "Produced by", "Bottled by", "Distilled by", "Made by". Extract ONLY the company name, not the surrounding phrase
- producer_address: The physical location (city, state/country) of the producer. Do NOT extract production statements like "Produced and Bottled in Germany" -- look for an actual city name
- country_of_origin: The country where the product was made. Look for "Product of [country]", "Made in [country]", "Produced in [country]"
- importer_name: The importing company name. Look for text AFTER "Imported by" -- extract the company name (e.g. "Sidney Frank Importing Co., Inc."), NOT the "Imported by" prefix itself
- importer_address: The city and state of the importer, usually printed directly after the importer company name (e.g. "New Rochelle, N.Y.")
- government_warning: CRITICAL -- include the "GOVERNMENT WARNING:" prefix, then the full text with both numbered points about (1) pregnancy and (2) driving/machinery. Extract every word verbatim
- sulfites_declaration: Look for "Contains Sulfites" or similar declaration
- Return ONLY the JSON object"""

# Focused prompt for government warning re-extraction (fix #2)
WARNING_REEXTRACT_PROMPT = """You are an expert text reader for US alcohol label compliance. Your ONLY task is to extract the GOVERNMENT WARNING text from this label image.

Focus on finding the block of text that starts with "GOVERNMENT WARNING:" -- it is a legally required statement on all US alcohol labels. It contains two numbered points:
(1) About women not drinking during pregnancy / risk of birth defects
(2) About consumption impairing ability to drive / operate machinery / health problems

Read EVERY SINGLE WORD carefully, character by character. Pay special attention to:
- The exact wording in point (2): it should say "CONSUMPTION OF ALCOHOLIC BEVERAGES" (not just "ALCOHOL")
- Every word matters for compliance -- do NOT skip, summarize, or paraphrase

Return ONLY a JSON object (no markdown, no extra text):
{"government_warning": {"value": null, "conf": "high"}}

Rules:
- Replace null with the full verbatim text starting from "GOVERNMENT WARNING:" through the end of the statement
- conf: "high" = clearly readable, "medium" = partially obscured, "low" = barely legible
- If no government warning is visible on this label, return null
- Extract EXACTLY as printed -- do NOT correct errors"""

# Focused prompt for importer re-extraction when initial pass returns null
IMPORTER_REEXTRACT_PROMPT = """You are an expert text reader for US alcohol label compliance. Your ONLY task is to find and extract the IMPORTER information from this label image.

Look carefully for text containing "IMPORTED BY" or "IMPORTER" -- this is usually printed in small text near the bottom of the label or on the back panel, often near the government warning or barcode.

The importer line typically follows this pattern:
IMPORTED BY [Company Name], [City], [State]

Examples:
- "IMPORTED BY SIDNEY FRANK IMPORTING CO. INC. NEW ROCHELLE, N.Y."
- "IMPORTED BY NICHE W. & S., CEDAR KNOLLS, NJ"
- "IMPORTED BY KOBRAND CORPORATION, NEW YORK, N.Y."

Read every word carefully, especially small text at the bottom of the label.

Return ONLY a JSON object (no markdown, no extra text):
{"importer_name": {"value": null, "conf": "high"}, "importer_address": {"value": null, "conf": "high"}}

Rules:
- importer_name: The company name AFTER "IMPORTED BY". Do NOT include the "IMPORTED BY" prefix.
- importer_address: The city and state that follow the company name.
- conf: "high" = clearly readable, "medium" = partially obscured, "low" = barely legible
- If no importer information is visible, return null for both fields
- Extract EXACTLY as printed -- do NOT correct errors"""


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


@dataclass
class ExtractionResult:
    fields: dict = field(default_factory=dict)
    panel_type: str = ""
    extraction_notes: str = ""
    error: str | None = None


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


class BaseExtractor(abc.ABC):
    @abc.abstractmethod
    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract all fields from a label image."""


class GroqExtractor(BaseExtractor):
    def __init__(self, api_key: str, model: str = "meta-llama/llama-4-maverick-17b-128e-instruct"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract all fields from a label image using a single LLM call."""
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{base64_image}"

        try:
            parsed = await self._call_llm_with_retry(image_url, EXTRACTION_PROMPT, panel_type)
        except Exception as e:
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Extraction failed: {e}",
            )

        # Convert parsed JSON to the expected format: {"field": {"value": ..., "bounding_box": None, "extraction_confidence": ...}}
        fields = {}
        for key, value in parsed.items():
            if key in ("fields", "extraction_notes"):
                continue
            # Handle nested confidence format: {"value": "...", "conf": "high"}
            if isinstance(value, dict) and "value" in value:
                fields[key] = {
                    "value": value["value"],
                    "bounding_box": None,
                    "extraction_confidence": value.get("conf", "high"),
                }
            else:
                # Legacy flat format: plain string or null
                fields[key] = {
                    "value": value,
                    "bounding_box": None,
                    "extraction_confidence": "high",
                }

        return ExtractionResult(
            fields=fields,
            panel_type=panel_type,
        )

    async def _call_llm_with_retry(
        self, image_url: str, prompt: str, panel_type: str
    ) -> dict:
        """Call LLM with exponential backoff retry on rate limit errors."""
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._call_llm(image_url, prompt, panel_type)
            except RateLimitError as e:
                last_error = e
                if attempt >= MAX_RETRIES:
                    break
                # Use retry-after header if available, otherwise exponential backoff
                retry_after = e.response.headers.get("retry-after")
                if retry_after:
                    delay = float(retry_after)
                else:
                    delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "Rate limited (attempt %d/%d, %s), retrying in %.1fs...",
                    attempt + 1, MAX_RETRIES, panel_type, delay,
                )
                await asyncio.sleep(delay)

        raise last_error

    async def _call_llm(self, image_url: str, prompt: str, panel_type: str) -> dict:
        """Make a single LLM call and return parsed JSON dict."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            response_text = response.choices[0].message.content
            logger.info("Groq response (%s): %s", panel_type, response_text[:200])

            parsed = _repair_json(response_text)
            if parsed is None:
                logger.error("JSON parse error (%s): %s", panel_type, response_text[:200])
                return {}

            return parsed

        except RateLimitError:
            raise
        except Exception as e:
            logger.exception("Extraction API call failed (%s): %s", panel_type, e)
            raise


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


class AnthropicExtractor(BaseExtractor):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        """Extract all fields from a label image using Anthropic's vision API."""
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
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
                                "text": EXTRACTION_PROMPT,
                            },
                        ],
                    }
                ],
            )

            response_text = response.content[0].text
            logger.info("Anthropic response (%s): %s", panel_type, response_text[:200])

            parsed = _repair_json(response_text)
            if parsed is None:
                logger.error("JSON parse error (%s): %s", panel_type, response_text[:200])
                return ExtractionResult(fields={}, panel_type=panel_type)

            fields = _convert_parsed_to_fields(parsed)

            # Second pass: re-extract government warning with focused prompt.
            # Always attempt re-extraction — the focused prompt is more accurate
            # for reading warnings that are rotated, small, or partially obscured.
            gw_field = fields.get("government_warning", {})
            reextracted = await self.reextract_warning(image_bytes, mime_type)
            if reextracted:
                old_val = gw_field.get("value") if isinstance(gw_field, dict) else gw_field
                if old_val != reextracted:
                    logger.info("Warning re-extraction updated value for %s", panel_type)
                fields["government_warning"] = {
                    "value": reextracted,
                    "bounding_box": None,
                    "extraction_confidence": gw_field.get("extraction_confidence", "high") if isinstance(gw_field, dict) else "high",
                }

            # Third pass: re-extract importer info if missing.
            # Small importer text is often missed on the first pass.
            imp_field = fields.get("importer_name", {})
            imp_val = imp_field.get("value") if isinstance(imp_field, dict) else imp_field
            if not imp_val:
                reextracted_imp = await self.reextract_importer(image_bytes, mime_type)
                if reextracted_imp:
                    for key in ("importer_name", "importer_address"):
                        val = reextracted_imp.get(key)
                        if val:
                            fields[key] = {
                                "value": val,
                                "bounding_box": None,
                                "extraction_confidence": "medium",
                            }
                            logger.info("Importer re-extraction found %s for %s", key, panel_type)

            return ExtractionResult(fields=fields, panel_type=panel_type)

        except Exception as e:
            logger.exception("Anthropic extraction failed (%s): %s", panel_type, e)
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Extraction failed: {e}",
            )

    async def reextract_warning(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        model_override: str | None = None,
    ) -> str | None:
        """Re-extract just the government warning with a focused prompt.

        Args:
            image_bytes: The label image.
            mime_type: Image MIME type.
            model_override: Use a different model (e.g. Sonnet) for this call.

        Returns:
            The extracted warning text, or None on failure.
        """
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        model = model_override or self.model

        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=1024,
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
                                "text": WARNING_REEXTRACT_PROMPT,
                            },
                        ],
                    }
                ],
            )

            response_text = response.content[0].text
            logger.info("Warning re-extraction (%s): %s", model, response_text[:200])

            parsed = _repair_json(response_text)
            if parsed is None:
                return None

            gw = parsed.get("government_warning")
            if isinstance(gw, dict) and "value" in gw:
                return gw["value"]
            return gw

        except Exception as e:
            logger.exception("Warning re-extraction failed: %s", e)
            return None


    async def reextract_importer(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> dict | None:
        """Re-extract importer name and address with a focused prompt.

        Returns:
            Dict with importer_name and importer_address values, or None on failure.
        """
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
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
                                "text": IMPORTER_REEXTRACT_PROMPT,
                            },
                        ],
                    }
                ],
            )

            response_text = response.content[0].text
            logger.info("Importer re-extraction: %s", response_text[:200])

            parsed = _repair_json(response_text)
            if parsed is None:
                return None

            result = {}
            for key in ("importer_name", "importer_address"):
                field = parsed.get(key)
                if isinstance(field, dict) and "value" in field:
                    result[key] = field["value"]
                elif isinstance(field, str):
                    result[key] = field

            return result if any(result.values()) else None

        except Exception as e:
            logger.exception("Importer re-extraction failed: %s", e)
            return None

    async def reextract_specialty_class(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> dict | None:
        """Re-extract fanciful name and composition statement for specialty products.

        Returns:
            Dict with fanciful_name and composition_statement values, or None on failure.
        """
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
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
                                "text": SPECIALTY_CLASS_PROMPT,
                            },
                        ],
                    }
                ],
            )

            response_text = response.content[0].text
            logger.info("Specialty class re-extraction: %s", response_text[:200])

            parsed = _repair_json(response_text)
            if parsed is None:
                return None

            result = {}
            for key in ("fanciful_name", "composition_statement"):
                field = parsed.get(key)
                if isinstance(field, dict) and "value" in field:
                    result[key] = field["value"]
                elif isinstance(field, str):
                    result[key] = field

            return result if any(result.values()) else None

        except Exception as e:
            logger.exception("Specialty class re-extraction failed: %s", e)
            return None
