import hashlib
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.ocr_layout import REFERENCE_SIZE, matches_rectified_reference
from app.ocr_rectify import RectificationError, detect_page_corners, rectify_page

FIXTURE = Path(__file__).parent / "fixtures" / "aem_2023_blank.png"


def synthetic_photo():
    source = cv2.cvtColor(cv2.imread(str(FIXTURE)), cv2.COLOR_BGR2RGB)
    source = cv2.resize(source, (850, 1211))
    height, width = source.shape[:2]
    origin = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    corners = np.float32([[170, 125], [1005, 90], [1080, 1480], [115, 1510]])
    matrix = cv2.getPerspectiveTransform(origin, corners)
    photo = cv2.warpPerspective(source, matrix, (1200, 1600), flags=cv2.INTER_LINEAR, borderValue=(55, 55, 55))
    return Image.fromarray(photo), corners


def encoded(image):
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_perspective_and_orientation_recover_2023_grid():
    photo, expected = synthetic_photo()
    detected = detect_page_corners(np.asarray(photo))
    mean_corner_error = np.linalg.norm(detected - expected, axis=1).mean()
    assert mean_corner_error <= .02 * min(photo.size)
    original_bytes = FIXTURE.read_bytes()
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    photo_bytes = encoded(photo)
    result = rectify_page(photo_bytes)
    assert result.source_sha256 == hashlib.sha256(photo_bytes).hexdigest()
    assert result.image.size == REFERENCE_SIZE
    assert matches_rectified_reference(result.image)
    assert result.rotation_degrees == 0
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == original_sha
    turned = rectify_page(encoded(photo.rotate(90, expand=True)))
    assert turned.image.size == REFERENCE_SIZE
    assert matches_rectified_reference(turned.image)
    assert turned.rotation_degrees in (90, 270)
    upside_down = rectify_page(encoded(photo.rotate(180, expand=True)))
    assert matches_rectified_reference(upside_down.image)
    assert upside_down.rotation_degrees == 180


def test_rectification_rejects_non_page_and_preserves_source_digest():
    source = FIXTURE.read_bytes()
    result = rectify_page(source)
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.rotation_degrees == 0
    with pytest.raises(RectificationError):
        rectify_page(encoded(Image.new("RGB", (1200, 1600), "white")))
    photo, _ = synthetic_photo()
    with pytest.raises(RectificationError):
        rectify_page(encoded(photo.crop((150, 0, 1200, 1600))))
