"""Geometría provisional del A.E.M. 2023 para páginas ya rectificadas.

No clasifica fotografías ni lee texto. La geometría no se activa para 2026.
"""

from dataclasses import dataclass
import argparse
import json

from PIL import Image, ImageStat

REFERENCE_SIZE = (1871, 2667)
TEMPLATE_VERSION = "aem-2023-blank-reference-v1"
TABLE_X = (516, 562, 1125, 1697, 1866)
TABLE_Y = (
    829, 863, 901, 938, 982, 1027, 1069, 1109, 1150, 1190,
    1230, 1271, 1311, 1351, 1392, 1432, 1472, 1513, 1553, 1593,
    1634, 1674, 1714, 1755, 1795, 1835, 1876, 1916, 1956, 1997,
    2037, 2077, 2118, 2158, 2198, 2239, 2279, 2319, 2360, 2405, 2450,
)


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    def scaled(self, size: tuple[int, int]) -> "Box":
        width, height = size
        return Box(
            round(self.left * width / REFERENCE_SIZE[0]),
            round(self.top * height / REFERENCE_SIZE[1]),
            round(self.right * width / REFERENCE_SIZE[0]),
            round(self.bottom * height / REFERENCE_SIZE[1]),
        )


# Zonas amplias: los valores escritos se localizarán dentro de cada una con el OCR real.
# Se excluyen la columna de nombres/firmas (a la izquierda de la tabla) y el pie.
REGIONS = {
    "province": Box(12, 89, 390, 169),
    "island_optional": Box(400, 89, 734, 169),
    "municipality": Box(742, 89, 1188, 169),
    "district": Box(1200, 89, 1508, 169),
    "section": Box(1517, 89, 1692, 169),
    "table": Box(1703, 89, 1861, 169),
    "electors_and_certificates": Box(41, 309, 657, 702),
    "voters_and_interventors": Box(686, 309, 1277, 581),
    "null_and_blank_votes": Box(1312, 309, 1858, 497),
}


def _line_score(gray: Image.Image, axis: str, coordinate: int) -> float:
    width, height = gray.size
    pixels = gray.load()
    if axis == "x":
        sample = range(round(height * .35), round(height * .87), max(1, height // 500))
        return sum(pixels[coordinate, y] < 235 for y in sample) / len(sample)
    sample = range(round(width * .61), round(width * .90), max(1, width // 500))
    return sum(pixels[x, coordinate] < 235 for x in sample) / len(sample)


def matches_rectified_reference(image: Image.Image) -> bool:
    """Sólo acepta una página alineada con el ejemplo de 2023; no hace rectificación."""
    width, height = image.size
    if width < 800 or height < 1100 or abs(width / height - REFERENCE_SIZE[0] / REFERENCE_SIZE[1]) > .025:
        return False
    gray = image.convert("L")
    if ImageStat.Stat(gray).mean[0] < 170:
        return False
    for axis, anchors in (("x", (516, 1125, 1697, 1866)), ("y", (829, 1190, 1714, 2450))):
        length, reference = (width, REFERENCE_SIZE[0]) if axis == "x" else (height, REFERENCE_SIZE[1])
        radius = max(2, round(length * .003))
        for anchor in anchors:
            center = round(anchor * length / reference)
            if max(_line_score(gray, axis, point) for point in range(max(0, center-radius), min(length, center+radius+1))) < .50:
                return False
    return True


def field_regions(size: tuple[int, int]) -> dict[str, Box]:
    return {name: box.scaled(size) for name, box in REGIONS.items()}


def candidate_rows(size: tuple[int, int]) -> list[dict[str, Box | int]]:
    """40 renglones; no se infiere candidatura por posición ni se leen firmas."""
    result = []
    for index, (top, bottom) in enumerate(zip(TABLE_Y, TABLE_Y[1:]), 1):
        # Márgenes interiores para excluir bordes impresos.
        result.append({
            "row": index,
            "candidacy": Box(TABLE_X[1]+5, top+3, TABLE_X[2]-5, bottom-3).scaled(size),
            "votes_words": Box(TABLE_X[2]+5, top+3, TABLE_X[3]-5, bottom-3).scaled(size),
            "votes_number": Box(TABLE_X[3]+5, top+3, TABLE_X[4]-5, bottom-3).scaled(size),
        })
    return result


def main():
    parser = argparse.ArgumentParser(description="Inspección geométrica del modelo A.E.M. 2023 rectificado")
    parser.add_argument("image")
    args = parser.parse_args()
    with Image.open(args.image) as image:
        matched = matches_rectified_reference(image)
        result = {"template_version": TEMPLATE_VERSION, "size": image.size, "geometry_match": matched}
        if matched:
            result["regions"] = {name: vars(box) for name, box in field_regions(image.size).items()}
            result["candidate_rows"] = [{key: value if key == "row" else vars(value) for key, value in row.items()} for row in candidate_rows(image.size)]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
