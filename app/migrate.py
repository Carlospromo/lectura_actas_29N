from pathlib import Path
from sqlalchemy import text
from app.db import engine


def migrate():
    sql = (Path(__file__).resolve().parents[1] / "migrations/001_initial.sql").read_text()
    with engine.begin() as conn:
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))
        conn.execute(text("INSERT INTO elections(id,name,event_date,synthetic) VALUES (1,'ELECCIÓN SINTÉTICA LOCAL','2026-11-29',true) ON CONFLICT(id) DO NOTHING"))
        conn.execute(text("INSERT INTO territories(id,kind,code,name) VALUES (1,'province','TEST','PROVINCIA SINTÉTICA') ON CONFLICT(id) DO NOTHING"))
        conn.execute(text("INSERT INTO polling_places(id,territory_id,name,synthetic) VALUES (1,1,'LOCAL SINTÉTICO',true) ON CONFLICT(id) DO NOTHING"))
        for tid, label in [(1, 'A'), (2, 'B')]:
            conn.execute(text("INSERT INTO polling_tables(id,place_id,province_code,municipality_code,district,section,label,synthetic) VALUES (:id,1,'TEST','TEST','01',:section,:label,true) ON CONFLICT(id) DO NOTHING"), {"id": tid, "section": f"00{tid}", "label": label})
        for uid, name, role, results in [(1,'Apoderado sintético A','apoderado',False),(2,'Apoderado sintético B','apoderado',False),(3,'Organización sintética','organizacion',True),(4,'Supervisor sintético','supervisor',True)]:
            conn.execute(text("INSERT INTO users(id,display_name,role,active,can_view_results,synthetic) VALUES (:id,:name,:role,true,:results,true) ON CONFLICT(id) DO NOTHING"), {"id":uid,"name":name,"role":role,"results":results})
        for uid, tid in [(1,1),(2,2),(4,1),(4,2)]:
            conn.execute(text("INSERT INTO assignments(user_id,table_id) VALUES (:uid,:tid) ON CONFLICT DO NOTHING"), {"uid":uid,"tid":tid})
        for cid, name in [(1,'CANDIDATURA SINTÉTICA 1'),(2,'CANDIDATURA SINTÉTICA 2')]:
            conn.execute(text("INSERT INTO candidacies(id,election_id,chamber,constituency_code,name,synthetic) VALUES (:id,1,'congreso','TEST',:name,true) ON CONFLICT(id) DO NOTHING"), {"id":cid,"name":name})


if __name__ == "__main__":
    migrate()
