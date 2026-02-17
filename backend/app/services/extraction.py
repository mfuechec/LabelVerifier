import base64
import json
from dataclasses import dataclass, field

import anthropic


EXTRACTION_PROMPT = """You are an alcohol beverage label analysis system for the US TTB (Alcohol and
Tobacco Tax and Trade Bureau). Extract all compliance-relevant fields from this
label image.

Return a JSON object with the following structure. For each field found, include
the extracted text and an approximate bounding box (x, y, width, height as
percentages of image dimensions, 0-100). If a field is not found, set its value
to null and omit the bounding_box.

{
  "fields": {
    "brand_name": {
      "value": "string or null",
      "bounding_box": {"x": 0, "y": 0, "width": 0, "height": 0}
    },
    "class_type": { "value": null, "bounding_box": null },
    "alcohol_content": { "value": null, "bounding_box": null },
    "alcohol_proof": { "value": null, "bounding_box": null },
    "net_contents": { "value": null, "bounding_box": null },
    "producer_name": { "value": null, "bounding_box": null },
    "producer_address": { "value": null, "bounding_box": null },
    "country_of_origin": { "value": null, "bounding_box": null },
    "importer_name": { "value": null, "bounding_box": null },
    "importer_address": { "value": null, "bounding_box": null },
    "government_warning": { "value": null, "bounding_box": null },
    "sulfites_declaration": { "value": null, "bounding_box": null }
  },
  "extraction_notes": "Any observations about image quality, readability, or ambiguous text"
}

Rules:
- Extract text EXACTLY as it appears on the label (preserve capitalization)
- For alcohol_content, extract the percentage value including format (e.g., "45% Alc./Vol.")
- For alcohol_proof, extract proof if separately stated (e.g., "90 Proof")
- For government_warning, extract the COMPLETE warning text verbatim
- Bounding boxes are percentage-based: x=0,y=0 is top-left; x=100,y=100 is bottom-right
- If text is partially obscured or hard to read, extract your best reading and note the issue in extraction_notes
- Return ONLY the JSON object, no other text"""


@dataclass
class ExtractionResult:
    fields: dict = field(default_factory=dict)
    panel_type: str = ""
    extraction_notes: str = ""
    error: str | None = None


class ExtractionService:
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def extract_fields(
        self,
        image_bytes: bytes,
        panel_type: str,
        mime_type: str = "image/jpeg",
    ) -> ExtractionResult:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
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

            try:
                data = json.loads(response_text)
                return ExtractionResult(
                    fields=data.get("fields", {}),
                    panel_type=panel_type,
                    extraction_notes=data.get("extraction_notes", ""),
                )
            except json.JSONDecodeError:
                return ExtractionResult(
                    panel_type=panel_type,
                    error=f"Failed to parse extraction response as JSON: {response_text[:200]}",
                )

        except Exception as e:
            return ExtractionResult(
                panel_type=panel_type,
                error=f"Extraction API call failed: {str(e)}",
            )
