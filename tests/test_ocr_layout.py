import hashlib
from pathlib import Path

from PIL import Image

from app.ocr_layout import REFERENCE_SIZE, TABLE_X, TEMPLATE_VERSION, candidate_rows, field_regions, matches_rectified_reference

FIXTURE = Path(__file__).parent / "fixtures" / "aem_2023_blank.png"
SOURCE_SHA256 = "9c673965eb4f8644f34ac652f19dcf4dba0ed40fa225ab7718bd2a5a54d579e3"


def test_2023_mesa_form_layout_and_provenance():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SOURCE_SHA256
    with Image.open(FIXTURE) as image:
        assert image.size == REFERENCE_SIZE
        assert TEMPLATE_VERSION.startswith("aem-2023-")
        assert matches_rectified_reference(image)
        regions = field_regions(image.size)
        assert {"province", "island_optional", "municipality", "district", "section", "table"} <= set(regions)
        assert regions["island_optional"].left < regions["municipality"].left
        rows = candidate_rows(image.size)
        assert len(rows) == 40
        assert [row["row"] for row in rows] == list(range(1, 41))
        assert all(row["candidacy"].left >= TABLE_X[1] for row in rows)
        assert all(row["votes_number"].right <= image.width for row in rows)
        assert all(row["candidacy"].bottom <= next_row["candidacy"].top for row, next_row in zip(rows, rows[1:]))
        assert rows[-1]["votes_number"].bottom < image.height


def test_layout_requires_rectified_grid_and_scales_without_reading_votes():
    with Image.open(FIXTURE) as image:
        half = image.resize((936, 1334))
        assert matches_rectified_reference(half)
        assert len(candidate_rows(half.size)) == 40
        assert not matches_rectified_reference(image.rotate(90, expand=True))
        assert not matches_rectified_reference(Image.new("RGB", image.size, "white"))
        assert not matches_rectified_reference(Image.new("RGB", image.size, "black"))
