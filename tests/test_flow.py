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
from app.db import engine, Session, one
from app.migrate import migrate
from sqlalchemy import text

migrate()

photo = io.BytesIO()
Image.new("RGB", (40, 40), "white").save(photo, format="JPEG")
OBJECTS = {}


class FakeS3:
    def get_object(self, Bucket, Key):
        if Key not in OBJECTS: raise KeyError(Key)
        return {"Body": io.BytesIO(OBJECTS[Key])}

    def copy_object(self, Bucket, CopySource, Key):
        OBJECTS[Key] = OBJECTS[CopySource["Key"]]

    def delete_object(self, Bucket, Key):
        OBJECTS.pop(Key, None)


main.client = lambda: FakeS3()
main.ensure_bucket = lambda: None
main.upload_url = lambda key, mime: "fake://" + key
main.read_url = lambda key: "fake://" + key


def login(uid):
    c = TestClient(main.app)
    r = c.post("/api/dev/login", json={"user_id": uid, "code": "TEST-ONLY-2026"})
    assert r.status_code == 200, r.text
    return c


def submit(c, table, idem):
    r = c.post("/api/documents", json={"table_id":table,"mime_type":"image/jpeg","idempotency_key":idem})
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
    assert org.get("/api/dashboard").json()["votes"] == [{"name":"CANDIDATURA SINTÉTICA 1","votes":100},{"name":"CANDIDATURA SINTÉTICA 2","votes":50}]
    # Same total, opposite distribution: preserve both and flag conflict.
    d2=submit(a,1,"second-upload")
    r=review(a,d2,{"1":50,"2":100})
    assert r.status_code == 200 and r.json()["conflict"] is True
    assert org.get("/api/dashboard").json()["validated_documents"] == 1
    assert org.get("/api/dashboard").json()["votes"][0]["votes"] == 50
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


def test_withdraw_updates_aggregates():
    a,supervisor,org=login(1),login(4),login(3)
    did=submit(a,1,"withdrawal-test")
    assert review(a,did,{"1":7,"2":3}).status_code==200
    assert a.post(f"/api/documents/{did}/withdraw").status_code==403
    assert supervisor.post(f"/api/documents/{did}/withdraw").status_code==200
    assert org.get("/api/dashboard").json()["validated_documents"]==0


def test_dashboard_counts_beyond_500():
    with Session.begin() as db:
        for tid in range(100, 601):
            db.execute(text("INSERT INTO polling_tables(id,place_id,province_code,municipality_code,district,section,label,synthetic) VALUES (:id,1,'TEST','TEST','99',:section,'A',true)"),{"id":tid,"section":str(tid)})
            db.execute(text("INSERT INTO documents(id,election_id,table_id,chamber,document_type,version,status,uploader_id,idempotency_key,current_validated,blank_votes,null_votes,total_votes) VALUES (:id,1,:tid,'congreso','escrutinio',1,'validated',1,:idem,true,0,0,1)"),{"id":f"bulk-{tid}","tid":tid,"idem":f"bulk-key-{tid}"})
            db.execute(text("INSERT INTO document_votes(document_id,candidacy_id,votes) VALUES (:id,1,1)"),{"id":f"bulk-{tid}"})
    data=login(3).get("/api/dashboard").json()
    assert data["validated_documents"]==501
    assert data["votes"][0]["votes"]==501
