"""Concilia los controles provinciales comunicados con el detalle de mesas 2023."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

from app.catalog import PROVINCES
from app.reference_import import parse_history

CONTROL_FIELDS = ("municipalities", "districts", "sections", "polling_tables", "polling_places")
REPORTED_TOTALS = {"municipalities": 8131, "districts": 10461, "sections": 36460, "polling_tables": 60314, "polling_places": 22706}
DEFAULT_CONTROLS = Path(__file__).resolve().parents[1] / "data/reference/2023_province_controls.csv"


def read_controls(path: Path = DEFAULT_CONTROLS):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ("province_code", "province_name", *CONTROL_FIELDS):
            raise ValueError("Cabecera de controles provinciales inválida")
        controls = {}
        for line, row in enumerate(reader, 2):
            p = row["province_code"]
            if p not in PROVINCES or p in controls or not row["province_name"].strip():
                raise ValueError(f"Fila {line}: provincia inválida o duplicada")
            try:
                values = {field: int(row[field]) for field in CONTROL_FIELDS}
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Fila {line}: recuento no entero") from exc
            if any(v < 0 for v in values.values()):
                raise ValueError(f"Fila {line}: recuento negativo")
            controls[p] = {"province_name": row["province_name"].strip(), **values}
    if set(controls) != PROVINCES:
        raise ValueError("Los controles no contienen las 52 provincias")
    totals = {field: sum(row[field] for row in controls.values()) for field in CONTROL_FIELDS}
    if totals != REPORTED_TOTALS:
        raise ValueError(f"Los controles no concilian con la fila TOTAL comunicada: {totals}")
    return controls, totals


def summarize_history(records):
    groups = defaultdict(lambda: {"municipalities": set(), "districts": set(), "sections": set(), "polling_tables": 0})
    for row in records:
        if row["is_exterior"]:
            continue
        p = row["province_code"]
        m = row["municipality_code"]
        d = row["district"]
        s = row["section"]
        groups[p]["municipalities"].add(m)
        groups[p]["districts"].add((m, d))
        groups[p]["sections"].add((m, d, s))
        groups[p]["polling_tables"] += 1
    return {p: {key: len(value) if isinstance(value, set) else value for key, value in group.items()} for p, group in groups.items()}


def compare(controls, actual):
    mismatches = []
    for p in sorted(PROVINCES):
        for field in CONTROL_FIELDS[:-1]:
            expected = controls[p][field]
            observed = actual.get(p, {}).get(field, 0)
            if observed != expected:
                mismatches.append({"province_code": p, "field": field, "reported": expected, "historical_detail": observed})
    return mismatches


def reconcile(workbook_path: Path, control_path: Path = DEFAULT_CONTROLS):
    controls, totals = read_controls(control_path)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True, keep_links=False)
    try:
        records, *_ = parse_history(workbook["MESAS"].values)
    finally:
        workbook.close()
    actual = summarize_history(records)
    mismatches = compare(controls, actual)
    return {"source": "controles provinciales comunicados para 2023", "provinces": 52, "reported_totals": totals, "verified_fields": list(CONTROL_FIELDS[:-1]), "polling_places": "solo total provincial comunicado; el detalle no identifica locales", "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description="Compara la tabla provincial comunicada con el Excel detallado de 2023")
    parser.add_argument("history_xlsx", type=Path)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    args = parser.parse_args()
    result = reconcile(args.history_xlsx, args.controls)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
