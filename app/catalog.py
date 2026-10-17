"""Importador de instantáneas electorales. Nunca descarga ni inventa mesas."""

import argparse
import csv
import hashlib
import io
import re
import uuid
from pathlib import Path

from sqlalchemy import text

from app.config import settings
from app.db import Session, all_rows, one
from app.migrate import migrate

FIELDS = (
    "province_code", "province_name", "municipality_code", "municipality_name",
    "place_code", "place_name", "district", "section", "table_label",
)
PROVINCES = {f"{n:02d}" for n in range(1, 53)}


def parse_rows(data: bytes, scope: str):
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Cabecera CSV distinta de la plantilla documentada")
        rows = []
        identities = set()
        provinces = {}
        municipalities = {}
        places = {}
        for number, raw in enumerate(reader, 2):
            if None in raw or any(v is None for v in raw.values()):
                raise ValueError(f"Fila {number}: columnas inválidas")
            row = {k: v.strip() for k, v in raw.items()}
            if not all(row.values()) or any(len(v) > 200 for v in row.values()):
                raise ValueError(f"Fila {number}: valor vacío o demasiado largo")
            p, m = row["province_code"], row["municipality_code"]
            if scope == "national" and (p not in PROVINCES or not re.fullmatch(r"\d{5}", m) or not m.startswith(p)):
                raise ValueError(f"Fila {number}: códigos territoriales inválidos")
            if scope == "national" and m.endswith("999"):
                raise ValueError(f"Fila {number}: 999 representa voto exterior, no una mesa local asignable")
            if scope == "synthetic" and not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", p):
                raise ValueError(f"Fila {number}: código sintético inválido")
            if not re.fullmatch(r"\d{1,3}", row["district"]) or not re.fullmatch(r"\d{1,4}", row["section"]):
                raise ValueError(f"Fila {number}: distrito o sección inválidos")
            row["district"] = row["district"].zfill(2)
            row["section"] = row["section"].zfill(3)
            row["table_label"] = row["table_label"].upper()
            key = (p, m, row["district"], row["section"], row["table_label"])
            if key in identities:
                raise ValueError(f"Fila {number}: mesa duplicada {key}")
            identities.add(key)
            for mapping, mapkey, value in (
                (provinces, p, row["province_name"]),
                (municipalities, m, row["municipality_name"]),
                (places, (p, m, row["place_code"]), row["place_name"]),
            ):
                if mapkey in mapping and mapping[mapkey] != value:
                    raise ValueError(f"Fila {number}: nombre contradictorio para {mapkey}")
                mapping[mapkey] = value
            rows.append(row)
    except UnicodeDecodeError as exc:
        raise ValueError("El CSV debe estar en UTF-8") from exc
    if not rows:
        raise ValueError("El catálogo no puede estar vacío")
    if scope == "national" and set(provinces) != PROVINCES:
        raise ValueError(f"Faltan provincias: {', '.join(sorted(PROVINCES-set(provinces)))}")
    return rows


def stage(path: Path, election_id: int, version: str, source_name: str, scope: str, source_url: str | None = None):
    if scope == "synthetic" and settings.app_env != "development":
        raise ValueError("Los catálogos sintéticos sólo se permiten en desarrollo")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", version):
        raise ValueError("Versión inválida")
    if not source_name.strip():
        raise ValueError("Indica la procedencia del archivo")
    data = path.read_bytes()
    rows = parse_rows(data, scope)
    digest = hashlib.sha256(data).hexdigest()
    with Session.begin() as db:
        election = one(db, "SELECT * FROM elections WHERE id=:id", {"id": election_id})
        if not election:
            raise ValueError("Elección inexistente")
        if bool(election["synthetic"]) != (scope == "synthetic"):
            raise ValueError("El alcance sintético debe coincidir con la elección")
        if one(db, "SELECT id FROM catalog_imports WHERE election_id=:eid AND version=:version", {"eid": election_id, "version": version}):
            raise ValueError("Versión ya importada; usa otro identificador")
        import_id = str(uuid.uuid4())
        db.execute(text("INSERT INTO catalog_imports(id,election_id,version,source_name,source_url,source_sha256,scope,row_count,status) VALUES (:id,:eid,:version,:source,:url,:sha,:scope,:count,'staged')"), {"id": import_id, "eid": election_id, "version": version, "source": source_name, "url": source_url, "sha": digest, "scope": scope, "count": len(rows)})
        for row in rows:
            db.execute(text("INSERT INTO catalog_rows(import_id,province_code,province_name,municipality_code,municipality_name,place_code,place_name,district,section,table_label) VALUES (:import_id,:province_code,:province_name,:municipality_code,:municipality_name,:place_code,:place_name,:district,:section,:table_label)"), {"import_id": import_id, **row})
    return {"id": import_id, "version": version, "rows": len(rows), "sha256": digest, "status": "staged"}


def _next_id(db, table):
    return db.execute(text(f"SELECT COALESCE(MAX(id),0)+1 FROM {table}")).scalar_one()


def _territory(db, kind, code, name, parent_id=None):
    existing = one(db, "SELECT * FROM territories WHERE kind=:kind AND code=:code", {"kind": kind, "code": code})
    if existing:
        if kind == "province" and existing["parent_id"] is None and parent_id is not None:
            db.execute(text("UPDATE territories SET parent_id=:parent WHERE id=:id"), {"parent": parent_id, "id": existing["id"]})
        elif not (kind == "province" and parent_id is None) and existing["parent_id"] != parent_id:
            raise ValueError(f"Territorio {kind}/{code} cambia de ámbito padre")
        # Los nombres de distintas fuentes o épocas se conservan en sus filas versionadas.
        # La denominación canónica existente no se reescribe de forma silenciosa.
        return existing["id"]
    new_id = _next_id(db, "territories")
    db.execute(text("INSERT INTO territories(id,parent_id,kind,code,name) VALUES (:id,:parent,:kind,:code,:name)"), {"id": new_id, "parent": parent_id, "kind": kind, "code": code, "name": name})
    return new_id


def activate(import_id: str):
    with Session.begin() as db:
        item = one(db, "SELECT * FROM catalog_imports WHERE id=:id", {"id": import_id})
        if not item or item["status"] != "staged":
            raise ValueError("Importación inexistente o no pendiente")
        # Serializa activaciones del mismo proceso en PostgreSQL.
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT id FROM elections WHERE id=:id FOR UPDATE"), {"id": item["election_id"]})
        rows = all_rows(db, "SELECT * FROM catalog_rows WHERE import_id=:id ORDER BY province_code,municipality_code,district,section,table_label", {"id": import_id})
        for row in rows:
            province_id = _territory(db, "province", row["province_code"], row["province_name"])
            municipality_id = _territory(db, "municipality", row["municipality_code"], row["municipality_name"], province_id)
            place = one(db, "SELECT * FROM catalog_places WHERE election_id=:eid AND province_code=:p AND municipality_code=:m AND place_code=:c", {"eid": item["election_id"], "p": row["province_code"], "m": row["municipality_code"], "c": row["place_code"]})
            if place and place["place_name"] != row["place_name"]:
                raise ValueError("El mismo código de local tiene otro nombre; revisar antes de activar")
            if not place:
                place_id = _next_id(db, "polling_places")
                db.execute(text("INSERT INTO polling_places(id,territory_id,name,synthetic) VALUES (:id,:mid,:name,:synthetic)"), {"id": place_id, "mid": municipality_id, "name": row["place_name"], "synthetic": item["scope"] == "synthetic"})
                db.execute(text("INSERT INTO catalog_places(election_id,province_code,municipality_code,place_code,place_id,place_name) VALUES (:eid,:p,:m,:c,:pid,:name)"), {"eid": item["election_id"], "p": row["province_code"], "m": row["municipality_code"], "c": row["place_code"], "pid": place_id, "name": row["place_name"]})
            else:
                place_id = place["place_id"]
            identity = {"province": row["province_code"], "municipality": row["municipality_code"], "district": row["district"], "section": row["section"], "label": row["table_label"]}
            table = one(db, "SELECT * FROM polling_tables WHERE province_code=:province AND municipality_code=:municipality AND district=:district AND section=:section AND label=:label", identity)
            if table and table["place_id"] != place_id:
                raise ValueError(f"La mesa {identity} cambia de local; revisar antes de activar")
            if not table:
                table_id = _next_id(db, "polling_tables")
                db.execute(text("INSERT INTO polling_tables(id,place_id,province_code,municipality_code,district,section,label,synthetic) VALUES (:id,:place_id,:province,:municipality,:district,:section,:label,:synthetic)"), {"id": table_id, "place_id": place_id, "synthetic": item["scope"] == "synthetic", **identity})
            else:
                table_id = table["id"]
            db.execute(text("UPDATE catalog_rows SET table_id=:tid WHERE import_id=:iid AND province_code=:province AND municipality_code=:municipality AND district=:district AND section=:section AND table_label=:label"), {"tid": table_id, "iid": import_id, **identity})
        db.execute(text("UPDATE catalog_imports SET status='superseded' WHERE election_id=:eid AND status='active'"), {"eid": item["election_id"]})
        db.execute(text("UPDATE catalog_imports SET status='active',activated_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id": import_id})
    return {"id": import_id, "status": "active", "rows": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="Catálogo electoral versionado; CSV UTF-8, sin descargas automáticas")
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
            print(all_rows(db, "SELECT id,election_id,version,source_name,source_url,source_sha256,scope,row_count,status,imported_at,activated_at FROM catalog_imports ORDER BY imported_at DESC"))


if __name__ == "__main__":
    main()
