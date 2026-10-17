"""Importa candidaturas de Congreso con procedencia y activación explícita."""

import argparse
import csv
import hashlib
import io
import re
import uuid
from pathlib import Path

from sqlalchemy import text

from app.catalog import PROVINCES
from app.config import settings
from app.db import Session, all_rows, one
from app.migrate import migrate

FIELDS = ("constituency_code", "candidacy_code", "candidacy_name")


def parse_rows(data: bytes, scope: str):
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Cabecera CSV de candidaturas inválida")
        rows, keys, names, constituencies = [], set(), set(), set()
        for number, raw in enumerate(reader, 2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"Fila {number}: columnas inválidas")
            row = {key: value.strip() for key, value in raw.items()}
            province, code, name = (row[field] for field in FIELDS)
            if not all(row.values()) or len(name) > 200 or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", code):
                raise ValueError(f"Fila {number}: candidatura inválida")
            if scope == "national" and province not in PROVINCES:
                raise ValueError(f"Fila {number}: circunscripción provincial inválida")
            if scope == "synthetic" and not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", province):
                raise ValueError(f"Fila {number}: circunscripción sintética inválida")
            key, named = (province, code), (province, name.casefold())
            if key in keys or named in names:
                raise ValueError(f"Fila {number}: candidatura duplicada en la circunscripción")
            keys.add(key)
            names.add(named)
            constituencies.add(province)
            rows.append(row)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("CSV de candidaturas no válido o no UTF-8") from exc
    if not rows:
        raise ValueError("El archivo de candidaturas está vacío")
    if scope == "national" and constituencies != PROVINCES:
        raise ValueError(f"Faltan circunscripciones: {', '.join(sorted(PROVINCES - constituencies))}")
    return rows


def stage(path: Path, election_id: int, version: str, source_name: str, scope: str, source_url: str | None = None):
    if scope not in ("national", "synthetic"):
        raise ValueError("Alcance inválido")
    if scope == "synthetic" and settings.app_env != "development":
        raise ValueError("Las candidaturas sintéticas sólo se permiten en desarrollo")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", version) or not source_name.strip():
        raise ValueError("Versión o procedencia inválida")
    data = path.read_bytes()
    rows = parse_rows(data, scope)
    digest = hashlib.sha256(data).hexdigest()
    with Session.begin() as db:
        election = one(db, "SELECT synthetic FROM elections WHERE id=:id", {"id": election_id})
        if not election or bool(election["synthetic"]) != (scope == "synthetic"):
            raise ValueError("Elección inexistente o alcance incompatible")
        if not one(db, "SELECT 1 AS ok FROM election_chambers WHERE election_id=:eid AND chamber='congreso' AND enabled=true", {"eid": election_id}):
            raise ValueError("Congreso no está habilitado para esta elección")
        if one(db, "SELECT 1 AS ok FROM candidacy_imports WHERE election_id=:eid AND chamber='congreso' AND version=:version", {"eid": election_id, "version": version}):
            raise ValueError("Versión de candidaturas ya importada")
        import_id = str(uuid.uuid4())
        db.execute(text("INSERT INTO candidacy_imports(id,election_id,chamber,version,source_name,source_url,source_sha256,scope,row_count,status) VALUES (:id,:eid,'congreso',:version,:source,:url,:sha,:scope,:count,'staged')"), {"id": import_id, "eid": election_id, "version": version, "source": source_name.strip(), "url": source_url, "sha": digest, "scope": scope, "count": len(rows)})
        for row in rows:
            db.execute(text("INSERT INTO candidacy_import_rows(import_id,constituency_code,candidacy_code,candidacy_name) VALUES (:id,:constituency_code,:candidacy_code,:candidacy_name)"), {"id": import_id, **row})
    return {"id": import_id, "version": version, "rows": len(rows), "sha256": digest, "status": "staged"}


def activate(import_id: str):
    with Session.begin() as db:
        item = one(db, "SELECT * FROM candidacy_imports WHERE id=:id", {"id": import_id})
        if not item or item["status"] != "staged":
            raise ValueError("Importación inexistente o no pendiente")
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT id FROM elections WHERE id=:id FOR UPDATE"), {"id": item["election_id"]})
            db.execute(text("LOCK TABLE documents IN SHARE MODE"))
            db.execute(text("LOCK TABLE candidacies IN SHARE ROW EXCLUSIVE MODE"))
        if one(db, "SELECT 1 AS ok FROM documents WHERE election_id=:eid AND chamber='congreso' LIMIT 1", {"eid": item["election_id"]}):
            raise ValueError("Ya existen actas de Congreso; no se puede cambiar su conjunto de candidaturas")
        rows = all_rows(db, "SELECT constituency_code,candidacy_code,candidacy_name FROM candidacy_import_rows WHERE import_id=:id ORDER BY constituency_code,candidacy_code", {"id": import_id})
        db.execute(text("UPDATE candidacy_imports SET status='superseded' WHERE election_id=:eid AND chamber='congreso' AND status='active'"), {"eid": item["election_id"]})
        next_id = db.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM candidacies")).scalar_one()
        for row in rows:
            cid = next_id
            next_id += 1
            db.execute(text("INSERT INTO candidacies(id,election_id,chamber,constituency_code,name,synthetic) VALUES (:id,:eid,'congreso',:province,:name,:synthetic)"), {"id": cid, "eid": item["election_id"], "province": row["constituency_code"], "name": row["candidacy_name"], "synthetic": item["scope"] == "synthetic"})
            db.execute(text("UPDATE candidacy_import_rows SET candidacy_id=:cid WHERE import_id=:iid AND constituency_code=:province AND candidacy_code=:code"), {"cid": cid, "iid": import_id, "province": row["constituency_code"], "code": row["candidacy_code"]})
        db.execute(text("UPDATE candidacy_imports SET status='active',activated_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id": import_id})
    return {"id": import_id, "status": "active", "rows": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="Candidaturas de Congreso versionadas; no descarga fuentes ni activa automáticamente")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("stage")
    s.add_argument("csv", type=Path)
    s.add_argument("--election-id", type=int, required=True)
    s.add_argument("--version", required=True)
    s.add_argument("--source-name", required=True)
    s.add_argument("--source-url")
    s.add_argument("--scope", choices=("national", "synthetic"), required=True)
    a = sub.add_parser("activate")
    a.add_argument("import_id")
    sub.add_parser("list")
    args = parser.parse_args()
    migrate()
    if args.command == "stage":
        print(stage(args.csv, args.election_id, args.version, args.source_name, args.scope, args.source_url))
    elif args.command == "activate":
        print(activate(args.import_id))
    else:
        with Session() as db:
            print(all_rows(db, "SELECT id,election_id,version,source_name,source_url,source_sha256,scope,row_count,status,imported_at,activated_at FROM candidacy_imports ORDER BY imported_at DESC"))


if __name__ == "__main__":
    main()
