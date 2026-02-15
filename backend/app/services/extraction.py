import base64
import json
import logging
import re
from dataclasses import dataclass, field

from groq import AsyncGroq

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are an alcohol beverage label analysis system for the US TTB (Alcohol and Tobacco Tax and Trade Bureau). Extract all compliance-relevant fields from this label image.

Return a JSON object with the following structure. For each field found, include the extracted text and an approximate bounding box (x, y, width, height as percentages of image dimensions, 0-100). If a field is not found, set its value to null and omit the bounding_box.

{"fields":{"brand_name":{"value":"string or null","bounding_box":{"x":0,"y":0,"width":0,"height":0}},"class_type":{"value":null,"bounding_box":null},"alcohol_content":{"value":null,"bounding_box":null},"alcohol_proof":{"value":null,"bounding_box":null},"net_contents":{"value":null,"bounding_box":null},"producer_name":{"value":null,"bounding_box":null},"producer_address":{"value":null,"bounding_box":null},"country_of_origin":{"value":null,"bounding_box":null},"importer_name":{"value":null,"bounding_box":null},"importer_address":{"value":null,"bounding_box":null},"government_warning":{"value":null,"bounding_box":null},"sulfites_declaration":{"value":null,"bounding_box":null}},"extraction_notes":"observations"}

Rules:
- Extract text EXACTLY as it appears on the label (preserve capitalization)
- For alcohol_content, extract the percentage value including format (e.g. "45% Alc./Vol.")
- For alcohol_proof, extract proof if separately stated (e.g. "90 Proof")
- For government_warning, extract the COMPLETE warning text verbatim
- Bounding boxes are percentage-based: x=0,y=0 is top-left; x=100,y=100 is bottom-right
- If text is partially obscured or hard to read, extract best reading and note in extraction_notes
- Return ONLY the JSON object, no other text"""


@dataclass
class ExtractionResult:
    fields: dict = field(default_factory=dict)
    panel_type: str = ""
    extraction_notes: str = ""
    error: str | None = None


class ExtractionService:
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)

    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
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

            response_text = response.choices[0].message.content
            logger.info("Groq response (%s): %s", panel_type, response_text[:200])

            # Strip markdown code fences if present
            cleaned = response_text.strip()
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            if fence_match:
                cleaned = fence_match.group(1).strip()

            try:
                data = json.loads(cleaned)
                return ExtractionResult(
                    fields=data.get("fields", {}),
                    panel_type=panel_type,
                    extraction_notes=data.get("extraction_notes", ""),
                )
            except json.JSONDecodeError:
                logger.error("JSON parse error (%s): %s", panel_type, cleaned[:200])
                return ExtractionResult(
                    panel_type=panel_type,
                    error=f"Failed to parse extraction response as JSON: {cleaned[:200]}",
                )

        except Exception as e:
            logger.exception("Extraction API call failed (%s): %s", panel_type, e)
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Extraction API call failed: {str(e)}",
            )
