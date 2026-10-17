"""Contrato preliminar de OCR. No valida modelos electorales aún no aprobados."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

DocumentKind = Literal["mesa_congreso", "mesa_senado", "cera_provincial", "unknown"]
CellKind = Literal["value", "zero", "blank", "absent", "illegible"]


def classify_heading(text: str) -> DocumentKind:
    """Clasificación conservadora de texto OCR; un resultado unknown requiere revisión."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    plain = re.sub(r"\s+", " ", plain)
    if "ACTA DE ESCRUTINIO" not in plain:
        return "unknown"
    if "RESIDENTES AUSENTES EN EL EXTRANJERO" in plain or "JUNTA ELECTORAL PROVINCIAL" in plain or "CERA" in plain:
        return "cera_provincial"
    if "MESA ELECTORAL" not in plain:
        return "unknown"
    if "CONGRESO DE LOS DIPUTADOS" in plain:
        return "mesa_congreso"
    if "SENADO" in plain:
        return "mesa_senado"
    return "unknown"


class NumericCell(BaseModel):
    kind: CellKind
    value: StrictInt | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def consistent(self):
        if self.kind == "value" and (self.value is None or self.value <= 0):
            raise ValueError("Una cifra positiva requiere entero mayor que cero")
        if self.kind == "zero" and self.value != 0:
            raise ValueError("El cero explícito requiere value=0")
        if self.kind in ("blank", "absent", "illegible") and self.value is not None:
            raise ValueError("Una casilla sin cifra no puede contener value")
        return self


class ProposedExtraction(BaseModel):
    document_kind: DocumentKind
    template_version: str | None = None
    total: NumericCell
    blank: NumericCell
    null: NumericCell
    votes: dict[str, NumericCell] = Field(default_factory=dict)
    note: str = ""
    model_config = {"extra": "forbid"}


def check_mesa_congreso(proposal: ProposedExtraction, candidacy_ids: set[str]):
    """Devuelve incidencias para revisión; nunca corrige o rellena cifras."""
    issues = []
    if proposal.document_kind != "mesa_congreso":
        issues.append("document_type_unverified")
    if set(proposal.votes) != candidacy_ids:
        issues.append("candidacy_set_mismatch")
    cells = [proposal.total, proposal.blank, proposal.null, *proposal.votes.values()]
    if any(cell.kind not in ("value", "zero") for cell in cells):
        issues.append("missing_or_unreadable_value")
    else:
        observed = proposal.blank.value + proposal.null.value + sum(cell.value for cell in proposal.votes.values())
        if observed != proposal.total.value:
            issues.append("sum_mismatch")
    return issues
