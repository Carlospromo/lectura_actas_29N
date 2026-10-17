import io
import os
from pathlib import Path

dbfile = Path(__file__).parent / "test.sqlite"
if dbfile.exists(): dbfile.unlink()
os.environ["DATABASE_URL"] = "sqlite:///" + dbfile.as_posix()
os.environ["APP_ENV"] = "development"

from fastapi.testclient import TestClient
from PIL import Image
from app import main, worker
from app import storage, storage_service
from app.db import engine, Session, one
from app.migrate import migrate
from app.catalog import stage, activate, parse_rows
from app.election import create as create_election, update_date
from app.candidacy_import import stage as stage_candidacies, activate as activate_candidacies, parse_rows as parse_candidacies
from sqlalchemy import text
from urllib.parse import urlsplit

migrate()

photo = io.BytesIO()
Image.new("RGB", (40, 40), "white").save(photo, format="JPEG")
OBJECTS = {}


main.get_object = lambda key: OBJECTS[key]
main.put_evidence = lambda key,data,mime: OBJECTS.__setitem__(key,data)
main.delete_staging = lambda key: OBJECTS.pop(key,None)
main.upload_url = lambda key, mime: "fake://" + key
main.read_url = lambda key,mime: "fake://" + key


def login(uid):
    c = TestClient(main.app)
    r = c.post("/api/dev/login", json={"user_id": uid, "code": "TEST-ONLY-2026"})
    assert r.status_code == 200, r.text
    return c


def submit(c, table, idem, **other):
    r = c.post("/api/documents", json={"table_id":table,"mime_type":"image/jpeg","idempotency_key":idem, **other})
    assert r.status_code == 200, r.text
    d = r.json()
    OBJECTS[d["upload_url"].removeprefix("fake://")] = photo.getvalue()
    r = c.post(f"/api/documents/{d['id']}/complete")
    assert r.status_code == 200, r.text
    assert worker.process_one()
    return d["id"]


def review(c, did, votes, decision="validated"):
    total=sum(votes.values())
    return c.post(f"/api/documents/{did}/review", json={"decision":decision,"votes":votes,"blank":0,"null":0,"total":total})


def test_full_flow_permissions_conflicts_and_restart():
    anon = TestClient(main.app)
    assert anon.get("/api/tables").status_code == 401
    assert anon.get("/api/dashboard").status_code == 401
    a,b,org=login(1),login(2),login(3)
    assert [t["id"] for t in a.get("/api/tables").json()] == [1]
    assert a.post("/api/documents",json={"table_id":2,"mime_type":"image/jpeg","idempotency_key":"forbidden-1"}).status_code == 403
    assert a.get("/api/dashboard").status_code == 403
    assert org.post("/api/documents",json={"table_id":1,"mime_type":"image/jpeg","idempotency_key":"forbidden-2"}).status_code == 403
    d1=submit(a,1,"first-upload")
    assert b.get(f"/api/documents/{d1}").status_code == 403
    assert b.get(f"/api/documents/{d1}/image").status_code == 403
    assert a.get(f"/api/documents/{d1}/image").status_code == 200
    assert org.get("/api/dashboard").json()["validated_documents"] == 0
    assert review(a,d1,{"1":100,"2":50}).status_code == 200
    assert org.get("/api/dashboard").json()["votes"] == [{"id":1,"name":"CANDIDATURA SINTÉTICA 1","votes":100},{"id":2,"name":"CANDIDATURA SINTÉTICA 2","votes":50}]
    # Same total, opposite distribution: preserve both and flag conflict.
    d2=submit(a,1,"second-upload")
    r=review(a,d2,{"1":50,"2":100})
    assert r.status_code == 200 and r.json()["conflict"] is True and r.json()["resolution_pending"] is True
    assert org.get("/api/dashboard").json()["validated_documents"] == 1
    assert org.get("/api/dashboard").json()["votes"][0]["votes"] == 100
    assert len(org.get("/api/conflicts").json()) == 1
    assert org.get(f"/api/documents/{d2}").json()["review"]["values"]["votes"]=={"1":50,"2":100}
    assert a.post(f"/api/conflicts/{d2}/resolve",json={"decision":"accept_new","reason":"Comprobado en acta"}).status_code == 403
    assert org.post(f"/api/conflicts/{d2}/resolve",json={"decision":"accept_new","reason":"Comprobado en acta"}).status_code == 200
    assert org.get("/api/dashboard").json()["votes"][0]["votes"] == 50
    assert org.get("/api/conflicts").json() == []
    assert a.get(f"/api/documents/{d1}").status_code == 200
    # A rejected third submission cannot enter results.
    d3=submit(a,1,"third-upload")
    assert review(a,d3,{"1":0,"2":0},"rejected").status_code == 200
    assert org.get("/api/dashboard").json()["validated_documents"] == 1
    assert a.post(f"/api/documents/{d2}/review",json={"decision":"validated","votes":{"1":50,"2":100},"total":150}).status_code == 409
    same=a.post("/api/documents",json={"table_id":1,"mime_type":"image/jpeg","idempotency_key":"second-upload"})
    assert same.json()["id"] == d2
    with Session() as db:
        assert one(db,"SELECT COUNT(*) AS n FROM processing_jobs WHERE document_id=:id",{"id":d2})["n"] == 1
    engine.dispose()
    assert org.get("/api/dashboard").json()["validated_documents"] == 1
    assert len(a.get("/api/documents").json()) == 3


def test_invalid_votes_and_session_revoke():
    a=login(1)
    did=submit(a,1,"invalid-votes")
    assert review(a,did,{"1":1.5,"2":2}).status_code == 422
    assert review(a,did,{"1":-1,"2":2}).status_code == 422
    assert review(a,did,{"1":1}).status_code == 422
    assert a.post("/api/logout").status_code == 200
    assert a.get("/api/tables").status_code == 401


def test_upload_completion_role_and_idempotency_mime():
    a, org = login(1), login(3)
    payload = {"table_id":1,"mime_type":"image/jpeg","idempotency_key":"completion-role-check"}
    created = a.post("/api/documents", json=payload)
    assert created.status_code == 200
    did = created.json()["id"]
    assert org.post(f"/api/documents/{did}/complete").status_code == 403
    changed = a.post("/api/documents", json={**payload,"mime_type":"image/png"})
    assert changed.status_code == 409
    assert a.post("/api/documents", json=payload).json()["id"] == did
    with Session.begin() as db:
        db.execute(text("INSERT INTO users(id,display_name,role,active,can_view_results,synthetic) VALUES (5,'Otro apoderado sintético','apoderado',true,false,true)"))
        db.execute(text("INSERT INTO assignments(user_id,table_id) VALUES (5,1)"))
    other = login(5)
    assert other.post(f"/api/documents/{did}/complete").status_code == 403
    OBJECTS[created.json()["upload_url"].removeprefix("fake://")] = photo.getvalue()
    assert a.post(f"/api/documents/{did}/complete").status_code == 200
    assert worker.process_one()
    assert other.post(f"/api/documents/{did}/review", json={"decision":"validated","votes":{"1":1,"2":0},"total":1}).status_code == 403


def test_withdraw_updates_aggregates():
    a,supervisor,org=login(2),login(4),login(3)
    before=org.get("/api/dashboard").json()["validated_documents"]
    did=submit(a,2,"withdrawal-test")
    assert review(a,did,{"1":7,"2":3}).status_code==200
    assert org.get("/api/dashboard").json()["validated_documents"]==before+1
    assert a.post(f"/api/documents/{did}/withdraw").status_code==403
    assert supervisor.post(f"/api/documents/{did}/withdraw").status_code==200
    assert org.get("/api/dashboard").json()["validated_documents"]==before


def test_dashboard_counts_beyond_500():
    before=login(3).get("/api/dashboard").json()["validated_documents"]
    with Session.begin() as db:
        for tid in range(100, 601):
            db.execute(text("INSERT INTO polling_tables(id,place_id,province_code,municipality_code,district,section,label,synthetic) VALUES (:id,1,'TEST','TEST','99',:section,'A',true)"),{"id":tid,"section":str(tid)})
            db.execute(text("INSERT INTO documents(id,election_id,table_id,chamber,document_type,version,status,uploader_id,idempotency_key,current_validated,blank_votes,null_votes,total_votes) VALUES (:id,1,:tid,'congreso','escrutinio',1,'validated',1,:idem,true,0,0,1)"),{"id":f"bulk-{tid}","tid":tid,"idem":f"bulk-key-{tid}"})
            db.execute(text("INSERT INTO document_votes(document_id,candidacy_id,votes) VALUES (:id,1,1)"),{"id":f"bulk-{tid}"})
    data=login(3).get("/api/dashboard").json()
    assert data["validated_documents"]==before+501
    assert data["votes"][0]["votes"]>=501


def test_storage_signed_access_and_disk_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service,"ROOT",tmp_path)
    c=TestClient(storage_service.app)
    preflight=c.options("/objects/test",headers={"Origin":"http://localhost:8001","Access-Control-Request-Method":"PUT","Access-Control-Request-Headers":"content-type"})
    assert preflight.status_code==200
    key="elections/1/documents/test/original"
    url=storage.upload_url(key,"image/jpeg")
    path=urlsplit(url).path+"?"+urlsplit(url).query
    assert c.get("/objects/"+key).status_code==403
    assert c.put("/objects/"+key,content=photo.getvalue()).status_code==403
    assert c.put(path,content=photo.getvalue(),headers={"Content-Type":"image/jpeg"}).status_code==200
    assert c.get("/internal/objects/"+key).status_code==403
    assert (tmp_path/key).read_bytes()==photo.getvalue()
    evidence="elections/1/documents/test/evidence/hash"
    headers={"X-Storage-Secret":storage.settings.storage_secret}
    assert c.put("/internal/objects/"+evidence,content=photo.getvalue(),headers=headers).status_code==200
    assert c.get(urlsplit(storage.read_url(evidence)).path+"?"+urlsplit(storage.read_url(evidence)).query).content==photo.getvalue()


def test_chamber_configuration_and_senate_validation():
    a=login(1)
    assert a.post("/api/documents",json={"table_id":1,"chamber":"senado","mime_type":"image/jpeg","idempotency_key":"disabled-senate"}).status_code==422
    with Session.begin() as db:
        db.execute(text("INSERT INTO elections(id,name,event_date,synthetic) VALUES (2,'ELECCIÓN SENADO SINTÉTICA','2026-11-29',true)"))
        db.execute(text("INSERT INTO election_chambers(election_id,chamber,enabled) VALUES (2,'senado',true)"))
        db.execute(text("INSERT INTO election_document_types(election_id,chamber,document_type,enabled) VALUES (2,'senado','escrutinio',true)"))
        db.execute(text("INSERT INTO candidacies(id,election_id,chamber,constituency_code,name,synthetic) VALUES (10,2,'senado','TEST','LISTA SINTÉTICA',true)"))
        db.execute(text("INSERT INTO candidates(id,candidacy_id,name) VALUES (10,10,'CANDIDATO SINTÉTICO A'),(11,10,'CANDIDATO SINTÉTICO B')"))
    did=submit(a,1,"senate-test",election_id=2,chamber="senado")
    bad=a.post(f"/api/documents/{did}/review",json={"decision":"validated","candidate_votes":{"10":10},"total":10})
    assert bad.status_code==422
    # El Senado permite varios votos por elector; no se exige igualdad con el total de papeletas.
    good=a.post(f"/api/documents/{did}/review",json={"decision":"validated","candidate_votes":{"10":10,"11":8},"total":10})
    assert good.status_code==200,good.text
    with Session() as db:
        assert one(db,"SELECT COUNT(*) AS n FROM candidate_votes WHERE document_id=:id",{"id":did})["n"]==2


def test_catalog_versioned_stage_activate(tmp_path):
    header="province_code,province_name,municipality_code,municipality_name,place_code,place_name,district,section,table_label\n"
    line="SYN,PROVINCIA SINTÉTICA,SYN01,MUNICIPIO SINTÉTICO,L1,LOCAL SINTÉTICO,1,1,A\n"
    file=tmp_path/"catalog.csv"
    file.write_text(header+line,encoding="utf-8")
    assert len(parse_rows(file.read_bytes(),"synthetic"))==1
    try:
        parse_rows((header+line+line).encode(),"synthetic")
        assert False,"duplicado aceptado"
    except ValueError:
        pass
    try:
        parse_rows((header+"01,Madrid,01001,Municipio,L,Local,1,1,A\n").encode(),"national")
        assert False,"cobertura nacional incompleta aceptada"
    except ValueError:
        pass
    try:
        parse_rows((header+"01,PROVINCIA DE PRUEBA,01999,CERA01,L,LOCAL DE PRUEBA,9,0,U\n").encode(),"national")
        assert False,"voto exterior aceptado como mesa local"
    except ValueError as exc:
        assert "voto exterior" in str(exc)
    first=stage(file,1,"test-v1","Archivo sintético de prueba","synthetic")
    assert first["status"]=="staged"
    activated=activate(first["id"])
    assert activated["rows"]==1
    with Session() as db:
        table_id=one(db,"SELECT table_id FROM catalog_rows WHERE import_id=:id",{"id":first["id"]})["table_id"]
        assert table_id is not None
    second=stage(file,1,"test-v2","Archivo sintético de prueba","synthetic")
    activate(second["id"])
    with Session() as db:
        assert one(db,"SELECT status FROM catalog_imports WHERE id=:id",{"id":first["id"]})["status"]=="superseded"
        assert one(db,"SELECT table_id FROM catalog_rows WHERE import_id=:id",{"id":second["id"]})["table_id"]==table_id
    assert login(1).post("/api/documents",json={"table_id":1,"mime_type":"image/jpeg","idempotency_key":"out-of-catalog"}).status_code==422


def test_election_date_is_data():
    item=create_election("PROCESO SINTÉTICO DE PRUEBA","2026-11-29",synthetic=True)
    assert item["date_confirmed"] is False
    with Session() as db:
        assert one(db,"SELECT enabled FROM election_chambers WHERE election_id=:id AND chamber='senado'",{"id":item["id"]})["enabled"]==0
    changed=update_date(item["id"],"2026-12-06",date_confirmed=True)
    assert changed["event_date"]=="2026-12-06"


def test_versioned_candidacies_are_scoped_and_locked_after_documents(tmp_path):
    item = create_election("CANDIDATURAS SINTÉTICAS DE PRUEBA", "2026-11-29", synthetic=True)
    header = "constituency_code,candidacy_code,candidacy_name\n"
    rows = "TEST,L1,LISTA SINTÉTICA A\nTEST,L2,LISTA SINTÉTICA B\n"
    path = tmp_path / "candidacies.csv"
    path.write_text(header + rows, encoding="utf-8")
    assert len(parse_candidacies(path.read_bytes(), "synthetic")) == 2
    try:
        parse_candidacies((header + rows + rows).encode(), "synthetic")
        assert False, "Se aceptaron candidaturas duplicadas"
    except ValueError:
        pass
    try:
        parse_candidacies((header + "28,L1,PRUEBA\n").encode(), "national")
        assert False, "Se aceptó cobertura nacional incompleta"
    except ValueError:
        pass
    national = header + "".join(f"{province:02d},L1,LISTA DE PRUEBA {province:02d}\n" for province in range(1, 53))
    assert len(parse_candidacies(national.encode(), "national")) == 52
    first = stage_candidacies(path, item["id"], "ensayo-1", "Archivo sintético de prueba", "synthetic")
    assert first["status"] == "staged"
    assert activate_candidacies(first["id"])["rows"] == 2
    a, b = login(1), login(2)
    assert b.get(f"/api/candidacies?table_id=1&election_id={item['id']}").status_code == 403
    candidates = a.get(f"/api/candidacies?table_id=1&election_id={item['id']}").json()
    assert [c["code"] for c in candidates] == ["L1", "L2"]
    did = submit(a, 1, "candidacy-import-test", election_id=item["id"])
    votes = {str(candidates[0]["id"]): 7, str(candidates[1]["id"]): 3}
    assert review(a, did, votes).status_code == 200
    second = stage_candidacies(path, item["id"], "ensayo-2", "Archivo sintético de prueba", "synthetic")
    try:
        activate_candidacies(second["id"])
        assert False, "Se cambiaron candidaturas después de crear actas"
    except ValueError as exc:
        assert "actas" in str(exc)


def test_national_import_structure_covers_52_provinces(tmp_path):
    item=create_election("PRUEBA TÉCNICA NO OFICIAL","2026-11-29")
    header="province_code,province_name,municipality_code,municipality_name,place_code,place_name,district,section,table_label\n"
    lines=[f"{n:02d},PROVINCIA DE PRUEBA {n:02d},{n:02d}001,MUNICIPIO DE PRUEBA,LOCAL-1,LOCAL DE PRUEBA,01,001,A\n" for n in range(1,53)]
    file=tmp_path/"catalog_nacional_no_oficial.csv"
    file.write_text(header+"".join(lines),encoding="utf-8")
    staged=stage(file,item["id"],"prueba-52","Fixture temporal no oficial","national")
    assert activate(staged["id"])["rows"]==52
    result=login(3).get(f"/api/dashboard?election_id={item['id']}&chamber=congreso")
    assert result.status_code==200
    assert result.json()["assigned_tables_denominator"]==52
    with Session() as db:
        codes={r["province_code"] for r in db.execute(text("SELECT province_code FROM catalog_rows WHERE import_id=:id"),{"id":staged["id"]}).mappings()}
        assert {"51","52"}.issubset(codes)
