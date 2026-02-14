import os
import tempfile
from PIL import Image
import pytest
from app.services.annotation import AnnotationService


@pytest.fixture
def small_test_image():
    """Create a 100x100 white test image."""
    img = Image.new("RGB", (100, 100), "white")
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    yield path
    os.unlink(path)


@pytest.fixture
def annotation_service():
    return AnnotationService()


class TestAnnotationService:
    def test_annotate_with_green_box(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "brand_name",
                "status": "match",
                "bounding_box": {"x": 10, "y": 10, "width": 30, "height": 20},
            }
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        assert os.path.exists(output_path)

        img = Image.open(output_path)
        # Check green pixels exist in the bounding box region
        pixels = list(img.getdata())
        has_green = any(p[1] > 200 and p[0] < 100 and p[2] < 100 for p in pixels)
        assert has_green
        os.unlink(output_path)

    def test_annotate_with_red_box(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "government_warning",
                "status": "content_mismatch",
                "bounding_box": {"x": 10, "y": 50, "width": 80, "height": 40},
            }
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        img = Image.open(output_path)
        pixels = list(img.getdata())
        has_red = any(p[0] > 200 and p[1] < 100 and p[2] < 100 for p in pixels)
        assert has_red
        os.unlink(output_path)

    def test_annotate_with_yellow_box(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "class_type",
                "status": "extraction_uncertain",
                "bounding_box": {"x": 50, "y": 10, "width": 40, "height": 30},
            }
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        img = Image.open(output_path)
        pixels = list(img.getdata())
        has_yellow = any(p[0] > 200 and p[1] > 200 and p[2] < 100 for p in pixels)
        assert has_yellow
        os.unlink(output_path)

    def test_annotate_multiple_boxes(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "brand_name",
                "status": "match",
                "bounding_box": {"x": 5, "y": 5, "width": 40, "height": 15},
            },
            {
                "field_name": "abv",
                "status": "content_mismatch",
                "bounding_box": {"x": 5, "y": 50, "width": 40, "height": 15},
            },
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        img = Image.open(output_path)
        pixels = list(img.getdata())
        has_green = any(p[1] > 200 and p[0] < 100 and p[2] < 100 for p in pixels)
        has_red = any(p[0] > 200 and p[1] < 100 and p[2] < 100 for p in pixels)
        assert has_green
        assert has_red
        os.unlink(output_path)

    def test_output_saved_as_png(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "brand_name",
                "status": "match",
                "bounding_box": {"x": 10, "y": 10, "width": 30, "height": 20},
            }
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        assert output_path.endswith(".png")
        os.unlink(output_path)

    def test_skip_fields_without_bounding_box(self, small_test_image, annotation_service):
        field_results = [
            {
                "field_name": "brand_name",
                "status": "field_missing",
                "bounding_box": None,
            }
        ]
        output_path = annotation_service.annotate_image(
            small_test_image, field_results
        )
        assert os.path.exists(output_path)
        os.unlink(output_path)
