"""Alta explícita de procesos electorales; no incorpora datos de ejemplo."""

import argparse
from datetime import date

from sqlalchemy import text

from app.config import settings
from app.db import Session, all_rows, one
from app.migrate import migrate


def create(name: str, event_date: str, date_confirmed: bool = False, synthetic: bool = False):
    if not name.strip() or len(name) > 200:
        raise ValueError("Nombre de elección inválido")
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD") from exc
    if synthetic and settings.app_env != "development":
        raise ValueError("Elección sintética sólo permitida en desarrollo")
    with Session.begin() as db:
        new_id = db.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM elections")).scalar_one()
        db.execute(text("INSERT INTO elections(id,name,event_date,synthetic) VALUES (:id,:name,:date,:synthetic)"), {"id": new_id, "name": name.strip(), "date": parsed_date, "synthetic": synthetic})
        db.execute(text("INSERT INTO election_settings(election_id,date_confirmed,conflict_resolver_role) VALUES (:id,:confirmed,'organizacion')"), {"id": new_id, "confirmed": date_confirmed})
        for chamber, enabled in (("congreso", True), ("senado", False)):
            db.execute(text("INSERT INTO election_chambers(election_id,chamber,enabled) VALUES (:id,:chamber,:enabled)"), {"id": new_id, "chamber": chamber, "enabled": enabled})
            db.execute(text("INSERT INTO election_document_types(election_id,chamber,document_type,enabled) VALUES (:id,:chamber,'escrutinio',:enabled)"), {"id": new_id, "chamber": chamber, "enabled": enabled})
    return {"id": new_id, "name": name.strip(), "event_date": parsed_date.isoformat(), "date_confirmed": date_confirmed, "chamber": "congreso", "document_type": "escrutinio", "synthetic": synthetic}


def update_date(election_id: int, event_date: str, date_confirmed: bool = False):
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD") from exc
    with Session.begin() as db:
        if not one(db, "SELECT id FROM elections WHERE id=:id", {"id": election_id}):
            raise ValueError("Elección inexistente")
        db.execute(text("UPDATE elections SET event_date=:date WHERE id=:id"), {"date": parsed_date, "id": election_id})
        db.execute(text("UPDATE election_settings SET date_confirmed=:confirmed WHERE election_id=:id"), {"confirmed": date_confirmed, "id": election_id})
    return {"id": election_id, "event_date": parsed_date.isoformat(), "date_confirmed": date_confirmed}


def main():
    parser = argparse.ArgumentParser(description="Configuración explícita de elecciones; solo Congreso habilitado")
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument("--event-date", required=True)
    create_parser.add_argument("--date-confirmed", action="store_true")
    create_parser.add_argument("--synthetic", action="store_true")
    update_parser = sub.add_parser("update-date")
    update_parser.add_argument("election_id", type=int)
    update_parser.add_argument("--event-date", required=True)
    update_parser.add_argument("--date-confirmed", action="store_true")
    sub.add_parser("list")
    args = parser.parse_args()
    migrate()
    if args.command == "create":
        print(create(args.name, args.event_date, args.date_confirmed, args.synthetic))
    elif args.command == "update-date":
        print(update_date(args.election_id, args.event_date, args.date_confirmed))
    else:
        with Session() as db:
            print(all_rows(db, "SELECT e.id,e.name,e.event_date,e.synthetic,s.date_confirmed,s.conflict_resolver_role FROM elections e LEFT JOIN election_settings s ON s.election_id=e.id ORDER BY e.id"))


if __name__ == "__main__":
    main()
