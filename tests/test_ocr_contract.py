import pytest
from pydantic import ValidationError

from app.ocr_contract import NumericCell, ProposedExtraction, check_mesa_congreso, classify_heading


def proposal(**overrides):
    data = {
        "document_kind": "mesa_congreso",
        "total": {"kind": "value", "value": 150},
        "blank": {"kind": "zero", "value": 0},
        "null": {"kind": "zero", "value": 0},
        "votes": {"A": {"kind": "value", "value": 100}, "B": {"kind": "value", "value": 50}},
    }
    data.update(overrides)
    return ProposedExtraction.model_validate(data)


def test_cera_heading_is_not_a_mesa_acta():
    heading = "JUNTA ELECTORAL PROVINCIAL DE ... ACTA DE ESCRUTINIO PARA LA VOTACIÓN DE LOS RESIDENTES AUSENTES EN EL EXTRANJERO"
    assert classify_heading(heading) == "cera_provincial"
    assert classify_heading("ACTA DE ESCRUTINIO MESA ELECTORAL CONGRESO DE LOS DIPUTADOS") == "mesa_congreso"
    assert classify_heading("ACTA DE ESCRUTINIO") == "unknown"
    assert "document_type_unverified" in check_mesa_congreso(proposal(document_kind="cera_provincial"), {"A", "B"})


def test_ocr_cells_preserve_zero_blank_absent_and_illegible():
    for kind in ("blank", "absent", "illegible"):
        assert NumericCell(kind=kind).value is None
    assert NumericCell(kind="zero", value=0).value == 0
    for invalid in ({"kind": "value", "value": 0}, {"kind": "value", "value": -1}, {"kind": "value", "value": 1.5}, {"kind": "zero"}, {"kind": "blank", "value": 0}):
        with pytest.raises(ValidationError):
            NumericCell.model_validate(invalid)


def test_proposal_flags_incomplete_and_inconsistent_values_without_fixing_them():
    assert check_mesa_congreso(proposal(), {"A", "B"}) == []
    incomplete = proposal(votes={"A": {"kind": "value", "value": 100}, "B": {"kind": "illegible"}})
    assert "missing_or_unreadable_value" in check_mesa_congreso(incomplete, {"A", "B"})
    inconsistent = proposal(votes={"A": {"kind": "value", "value": 50}, "B": {"kind": "value", "value": 50}})
    assert "sum_mismatch" in check_mesa_congreso(inconsistent, {"A", "B"})
    assert inconsistent.votes["A"].value == 50
