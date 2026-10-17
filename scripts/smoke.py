"""Integration smoke against real Compose services (synthetic data only)."""
import io
import sys
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

BASE = "http://localhost:8001"
ID_FILE = Path(".smoke-id")


def wait_ready():
    for _ in range(90):
        try:
            if httpx.get(BASE, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("API did not become ready")


def login(uid):
    client = httpx.Client(base_url=BASE, timeout=20)
    for _ in range(30):
        try:
            r = client.post("/api/dev/login", json={"user_id":uid,"code":"TEST-ONLY-2026"})
            r.raise_for_status()
            return client
        except httpx.HTTPError:
            time.sleep(2)
    raise RuntimeError("Database or API did not become ready for login")


def create():
    agent=login(1)
    image=io.BytesIO()
    Image.new("RGB",(100,100),"white").save(image,format="JPEG")
    def upload():
        payload={"table_id":1,"mime_type":"image/jpeg","idempotency_key":"smoke-"+str(uuid.uuid4())}
        r=agent.post("/api/documents",json=payload)
        r.raise_for_status()
        d=r.json()
        assert d["upload_url"].startswith("http://localhost:9000/")
        put=httpx.put(d["upload_url"],content=image.getvalue(),headers={"Content-Type":"image/jpeg"},timeout=30)
        put.raise_for_status()
        agent.post(f"/api/documents/{d['id']}/complete").raise_for_status()
        for _ in range(30):
            status=agent.get(f"/api/documents/{d['id']}").json()["status"]
            if status=="pending_review": return d["id"]
            time.sleep(1)
        raise RuntimeError(f"Worker did not finish: {status}")
    first=upload()
    r=agent.post(f"/api/documents/{first}/review",json={"decision":"validated","mesa_congreso_confirmed":True,"votes":{"1":100,"2":50},"blank":0,"null":0,"total":150})
    r.raise_for_status()
    org=login(3)
    assert org.get("/api/dashboard").json()["validated_documents"] >= 1
    second=upload()
    r=agent.post(f"/api/documents/{second}/review",json={"decision":"validated","mesa_congreso_confirmed":True,"votes":{"1":50,"2":100},"blank":0,"null":0,"total":150})
    r.raise_for_status()
    assert r.json()["resolution_pending"] is True
    assert org.get("/api/dashboard").json()["votes"][0]["votes"]==100
    assert any(c["document_id"]==second for c in org.get("/api/conflicts").json())
    org.post(f"/api/conflicts/{second}/resolve",json={"decision":"accept_new","reason":"Verificación sintética de integración"}).raise_for_status()
    assert org.get("/api/dashboard").json()["votes"][0]["votes"]==50
    ID_FILE.write_text(second)
    print("Created, resolved conflict and validated",second)


def verify():
    did=ID_FILE.read_text().strip()
    agent=login(1)
    d=agent.get(f"/api/documents/{did}")
    d.raise_for_status()
    assert d.json()["status"]=="validated"
    image=agent.get(f"/api/documents/{did}/image")
    image.raise_for_status()
    data=httpx.get(image.json()["url"],timeout=30)
    data.raise_for_status()
    assert len(data.content)>100
    org=login(3)
    assert org.get("/api/dashboard").json()["validated_documents"] >= 1
    assert org.get("/api/dashboard").json()["votes"][0]["votes"]==50
    print("Document, image, conflict decision and result survived service restart")


if __name__=="__main__":
    wait_ready()
    {"create":create,"verify":verify}[sys.argv[1]]()
