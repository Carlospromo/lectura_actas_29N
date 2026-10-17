import pytest
from pydantic import ValidationError

from app.ocr_contract import NumericCell, ProposedExtraction, TextCell, check_mesa_congreso, classify_heading


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
    assert classify_heading("ELECCIONES ACTA DE ESCRUTINIO AEM") == "mesa_unknown_chamber"
    assert classify_heading("ACTA DE ESCRUTINIO AEM " + "texto " * 30 + "SENADO") == "mesa_unknown_chamber"
    assert classify_heading("ACTA DE ESCRUTINIO") == "unknown"
    assert "document_type_unverified" in check_mesa_congreso(proposal(document_kind="cera_provincial"), {"A", "B"})


def test_ocr_cells_preserve_zero_blank_absent_and_illegible():
    for kind in ("blank", "absent", "illegible"):
        assert NumericCell(kind=kind).value is None
    assert NumericCell(kind="zero", value=0).value == 0
    for invalid in ({"kind": "value", "value": 0}, {"kind": "value", "value": -1}, {"kind": "value", "value": 1.5}, {"kind": "zero"}, {"kind": "blank", "value": 0}):
        with pytest.raises(ValidationError):
            NumericCell.model_validate(invalid)
    with pytest.raises(ValidationError):
        TextCell(kind="blank", value="MADRID")
    assert proposal().identity.island.kind == "absent"


def test_proposal_flags_incomplete_and_inconsistent_values_without_fixing_them():
    assert check_mesa_congreso(proposal(), {"A", "B"}) == []
    incomplete = proposal(votes={"A": {"kind": "value", "value": 100}, "B": {"kind": "illegible"}})
    assert "missing_or_unreadable_value" in check_mesa_congreso(incomplete, {"A", "B"})
    inconsistent = proposal(votes={"A": {"kind": "value", "value": 50}, "B": {"kind": "value", "value": 50}})
    assert "sum_mismatch" in check_mesa_congreso(inconsistent, {"A", "B"})
    assert inconsistent.votes["A"].value == 50


def test_2023_mesa_summary_equations_are_warnings():
    complete = proposal(summary={
        "electors_on_lists": {"kind": "value", "value": 500},
        "certificates_added": {"kind": "value", "value": 2},
        "certificates_corrected": {"kind": "value", "value": 3},
        "total_electors": {"kind": "value", "value": 502},
        "voters_registered": {"kind": "value", "value": 149},
        "voters_interventors": {"kind": "value", "value": 1},
    })
    assert check_mesa_congreso(complete, {"A", "B"}) == []
    altered = proposal(summary={**complete.summary.model_dump(), "total_electors": {"kind": "value", "value": 503}, "voters_registered": {"kind": "value", "value": 148}})
    assert set(check_mesa_congreso(altered, {"A", "B"})) == {"elector_total_mismatch", "voter_total_mismatch"}
    assert altered.summary.total_electors.value == 503


def test_votes_written_in_letters_are_kept_separately():
    extracted = proposal(votes_words={"A": {"kind": "value", "value": "CIEN"}})
    assert extracted.votes_words["A"].value == "CIEN"
    assert extracted.votes["A"].value == 100
