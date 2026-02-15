import os
import tempfile
from PIL import Image, ImageDraw, ImageFont


STATUS_COLORS = {
    "match": (0, 200, 0),           # Green
    "content_mismatch": (220, 0, 0), # Red
    "field_missing": (220, 0, 0),    # Red
    "extraction_uncertain": (230, 230, 0),  # Yellow
}

BOX_WIDTH = 3


class AnnotationService:
    """Generates annotated label images with color-coded bounding boxes."""

    def annotate_image(
        self,
        image_path: str,
        field_results: list[dict],
        output_path: str | None = None,
    ) -> str:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        width, height = img.size

        for field in field_results:
            bbox = field.get("bounding_box")
            if not bbox:
                continue

            status = field.get("status", "extraction_uncertain")
            color = STATUS_COLORS.get(status, (230, 230, 0))
            field_name = field.get("field_name", "")

            # Convert percentage-based bbox to pixel coordinates
            x = int(bbox["x"] / 100 * width)
            y = int(bbox["y"] / 100 * height)
            w = int(bbox["width"] / 100 * width)
            h = int(bbox["height"] / 100 * height)

            # Draw rectangle border
            for i in range(BOX_WIDTH):
                draw.rectangle(
                    [x - i, y - i, x + w + i, y + h + i],
                    outline=color,
                )

            # Draw field label above the box
            label = field_name.replace("_", " ").title()
            font = None
            for font_path in [
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]:
                try:
                    font = ImageFont.truetype(font_path, 12)
                    break
                except (OSError, IOError):
                    continue
            if font is None:
                font = ImageFont.load_default()

            text_bbox = draw.textbbox((0, 0), label, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]

            label_y = max(0, y - text_h - 4)
            draw.rectangle(
                [x, label_y, x + text_w + 4, label_y + text_h + 2],
                fill=color,
            )
            draw.text((x + 2, label_y), label, fill="white", font=font)

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)

        img.save(output_path, "PNG")
        return output_path
