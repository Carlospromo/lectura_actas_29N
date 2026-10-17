"""Contrato preliminar de OCR. No valida modelos electorales aún no aprobados."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

DocumentKind = Literal["mesa_congreso", "mesa_senado", "mesa_unknown_chamber", "cera_provincial", "unknown"]
CellKind = Literal["value", "zero", "blank", "absent", "illegible"]


def classify_heading(text: str) -> DocumentKind:
    """Clasificación conservadora de texto OCR; un resultado unknown requiere revisión."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    plain = re.sub(r"\s+", " ", plain)
    if "ACTA DE ESCRUTINIO" not in plain:
        return "unknown"
    if "RESIDENTES AUSENTES EN EL EXTRANJERO" in plain or "JUNTA ELECTORAL PROVINCIAL" in plain or "CERA" in plain:
        return "cera_provincial"
    title_context = plain.split("ACTA DE ESCRUTINIO", 1)[1][:120]
    if "CONGRESO DE LOS DIPUTADOS" in title_context:
        return "mesa_congreso"
    if "SENADO" in title_context:
        return "mesa_senado"
    if "MESA ELECTORAL" in plain or re.search(r"\bA\.?E\.?M\.?\b", plain):
        return "mesa_unknown_chamber"
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


class TextCell(BaseModel):
    kind: Literal["value", "blank", "absent", "illegible"]
    value: str | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def consistent(self):
        if self.kind == "value" and (not self.value or not self.value.strip()):
            raise ValueError("Texto visible requiere contenido")
        if self.kind != "value" and self.value is not None:
            raise ValueError("Texto no leído no puede contener contenido")
        return self


def absent_numeric():
    return NumericCell(kind="absent")


def absent_text():
    return TextCell(kind="absent")


class MesaIdentity(BaseModel):
    province: TextCell = Field(default_factory=absent_text)
    island: TextCell = Field(default_factory=absent_text)
    municipality: TextCell = Field(default_factory=absent_text)
    district: TextCell = Field(default_factory=absent_text)
    section: TextCell = Field(default_factory=absent_text)
    table: TextCell = Field(default_factory=absent_text)
    model_config = {"extra": "forbid"}


class MesaSummary(BaseModel):
    electors_on_lists: NumericCell = Field(default_factory=absent_numeric)
    certificates_added: NumericCell = Field(default_factory=absent_numeric)
    certificates_corrected: NumericCell = Field(default_factory=absent_numeric)
    total_electors: NumericCell = Field(default_factory=absent_numeric)
    voters_registered: NumericCell = Field(default_factory=absent_numeric)
    voters_interventors: NumericCell = Field(default_factory=absent_numeric)
    model_config = {"extra": "forbid"}


class ProposedExtraction(BaseModel):
    document_kind: DocumentKind
    template_version: str | None = None
    identity: MesaIdentity = Field(default_factory=MesaIdentity)
    summary: MesaSummary = Field(default_factory=MesaSummary)
    total: NumericCell
    blank: NumericCell
    null: NumericCell
    votes: dict[str, NumericCell] = Field(default_factory=dict)
    votes_words: dict[str, TextCell] = Field(default_factory=dict)
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
    summary = proposal.summary
    electors = (summary.electors_on_lists, summary.certificates_added, summary.total_electors)
    if all(cell.kind in ("value", "zero") for cell in electors):
        if electors[0].value + electors[1].value != electors[2].value:
            issues.append("elector_total_mismatch")
    voters = (summary.voters_registered, summary.voters_interventors, proposal.total)
    if all(cell.kind in ("value", "zero") for cell in voters):
        if voters[0].value + voters[1].value != voters[2].value:
            issues.append("voter_total_mismatch")
    return issues
