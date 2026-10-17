import json
import time
import uuid
from datetime import timedelta
from sqlalchemy import text
from app.db import Session, one
from app.main import now
from app.ocr_contract import ProposedExtraction


def process_one():
    with Session() as db:
        # A lease makes a crash recoverable; extraction insert and completion commit together.
        lock = " FOR UPDATE SKIP LOCKED" if db.bind.dialect.name == "postgresql" else ""
        job = one(db,"SELECT * FROM processing_jobs WHERE (status='queued' AND available_at<=:now) OR (status='leased' AND lease_until<:now) ORDER BY available_at,id LIMIT 1"+lock,{"now":now()})
        if not job:
            db.rollback()
            return False
        db.execute(text("UPDATE processing_jobs SET status='leased',attempts=attempts+1,lease_until=:lease WHERE id=:id"),{"lease":now()+timedelta(minutes=5),"id":job["id"]})
        db.execute(text("UPDATE documents SET status='processing',updated_at=:now WHERE id=:id"),{"now":now(),"id":job["document_id"]})
        db.commit()
    try:
        # The local extractor deliberately returns no invented values.
        raw=ProposedExtraction(document_kind="unknown",total={"kind":"absent"},blank={"kind":"absent"},null={"kind":"absent"},votes={},note="EXTRACCIÓN SIMULADA: confirmar que es acta de mesa de Congreso e introducir cifras manualmente").model_dump()
        with Session.begin() as db:
            db.execute(text("INSERT INTO extractions(id,document_id,provider,model_version,config_json,raw_json) VALUES (:id,:did,'simulated','dev-1',:config,:raw) ON CONFLICT(document_id) DO NOTHING"),{"id":str(uuid.uuid4()),"did":job["document_id"],"config":json.dumps({"mode":"development_only"}),"raw":json.dumps(raw)})
            db.execute(text("UPDATE documents SET status='pending_review',updated_at=:now WHERE id=:id"),{"now":now(),"id":job["document_id"]})
            db.execute(text("UPDATE processing_jobs SET status='done',lease_until=NULL WHERE id=:id"),{"id":job["id"]})
        return True
    except Exception as exc:
        with Session.begin() as db:
            attempts=one(db,"SELECT attempts FROM processing_jobs WHERE id=:id",{"id":job["id"]})["attempts"]
            db.execute(text("UPDATE processing_jobs SET status=:status,available_at=:available,lease_until=NULL,last_error=:error WHERE id=:id"),{"status":"failed" if attempts>=5 else "queued","available":now()+timedelta(seconds=min(300,2**attempts)),"error":str(exc)[:500],"id":job["id"]})
            db.execute(text("UPDATE documents SET status='recoverable_error' WHERE id=:id"),{"id":job["document_id"]})
        return True


if __name__ == "__main__":
    while True:
        try:
            if not process_one(): time.sleep(1)
        except Exception as exc:
            print(f"worker polling error: {exc}",flush=True)
            time.sleep(3)
