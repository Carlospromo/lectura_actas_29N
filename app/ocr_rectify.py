"""Piloto de rectificación A.E.M. 2023, fuera del trabajador operativo.

Detecta una hoja completa, corrige perspectiva y verifica la cuadrícula.
No reconoce texto ni modifica el original.
"""

import argparse
import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.ocr_layout import REFERENCE_SIZE, TEMPLATE_VERSION, matches_rectified_reference


class RectificationError(ValueError):
    pass


@dataclass(frozen=True)
class RectificationResult:
    image: Image.Image
    source_sha256: str
    rotation_degrees: int
    corners_on_rotated_input: tuple[tuple[float, float], ...]
    template_version: str = TEMPLATE_VERSION


def order_corners(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    ordered = np.array([points[np.argmin(sums)], points[np.argmin(differences)], points[np.argmax(sums)], points[np.argmax(differences)]], dtype=np.float32)
    if len({tuple(point) for point in ordered}) != 4:
        raise RectificationError("Esquinas de página ambiguas")
    return ordered


def detect_page_corners(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    candidates = []
    for mask in (
        cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        cv2.Canny(blurred, 50, 150),
    ):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < width * height * .25:
                continue
            perimeter = cv2.arcLength(contour, True)
            polygon = cv2.approxPolyDP(contour, .018 * perimeter, True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue
            corners = order_corners(polygon)
            margin = max(3, round(min(width, height) * .003))
            if any(x <= margin or x >= width-margin or y <= margin or y >= height-margin for x, y in corners):
                continue
            top = np.linalg.norm(corners[1] - corners[0])
            bottom = np.linalg.norm(corners[2] - corners[3])
            left = np.linalg.norm(corners[3] - corners[0])
            right = np.linalg.norm(corners[2] - corners[1])
            ratio = (top + bottom) / (left + right)
            if not .50 <= ratio <= 1.95:
                continue
            candidates.append((area, corners))
    if not candidates:
        raise RectificationError("No se detecta una hoja completa con cuatro esquinas")
    return max(candidates, key=lambda item: item[0])[1]


def rectify_page(source_bytes: bytes) -> RectificationResult:
    """Rectify an encoded source image while retaining its exact byte digest."""
    with Image.open(BytesIO(source_bytes)) as image:
        original = ImageOps.exif_transpose(image).convert("RGB")
    digest = hashlib.sha256(source_bytes).hexdigest()
    if matches_rectified_reference(original):
        width, height = original.size
        corners = ((0.0, 0.0), (float(width-1), 0.0), (float(width-1), float(height-1)), (0.0, float(height-1)))
        return RectificationResult(original.copy(), digest, 0, corners)
    rgb = np.asarray(original)
    target = np.array([[0, 0], [REFERENCE_SIZE[0]-1, 0], [REFERENCE_SIZE[0]-1, REFERENCE_SIZE[1]-1], [0, REFERENCE_SIZE[1]-1]], dtype=np.float32)
    for quarter_turns in range(4):
        rotated = np.ascontiguousarray(np.rot90(rgb, quarter_turns))
        try:
            corners = detect_page_corners(rotated)
        except RectificationError:
            continue
        transform = cv2.getPerspectiveTransform(corners, target)
        rectified = cv2.warpPerspective(rotated, transform, REFERENCE_SIZE, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        result = Image.fromarray(rectified)
        if matches_rectified_reference(result):
            return RectificationResult(result, digest, (quarter_turns * 90) % 360, tuple(tuple(map(float, point)) for point in corners))
    raise RectificationError("Hoja detectada, pero no coincide con la cuadrícula A.E.M. 2023")


def main():
    parser = argparse.ArgumentParser(description="Rectifica un ensayo A.E.M. 2023 sin sobrescribir el original")
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, help="PNG derivado para inspección local")
    args = parser.parse_args()
    source = args.image.read_bytes()
    result = rectify_page(source)
    if args.output:
        if args.output.resolve() == args.image.resolve():
            parser.error("La salida no puede sobrescribir la imagen original")
        result.image.save(args.output)
    print(json.dumps({"template_version": result.template_version, "source_sha256": result.source_sha256, "rotation_degrees": result.rotation_degrees, "corners_on_rotated_input": result.corners_on_rotated_input, "rectified_size": result.image.size, "output": str(args.output) if args.output else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
