import hashlib
import io
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import text
from sqlalchemy.orm import Session
from PIL import Image

from app.config import settings
from app.db import db_session, one, all_rows
from app.storage import get_object, put_evidence, delete_staging, upload_url, read_url

app = FastAPI(title="Actas 29N — desarrollo sintético")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fail(code=403, detail="Sin permiso"):
    raise HTTPException(code, detail)


def user(request: Request, db: Session = Depends(db_session)):
    token = request.cookies.get("actas_session")
    if not token:
        fail(401, "Inicia sesión")
    row = one(db, "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=:id AND s.revoked_at IS NULL AND s.expires_at>:now AND u.active=true", {"id":hashlib.sha256(token.encode()).hexdigest(),"now":now()})
    if not row:
        fail(401, "Sesión caducada o revocada")
    return row


def can_access(db, actor, table_id):
    if actor["role"] == "administrador":
        return True
    return bool(one(db, "SELECT 1 AS ok FROM assignments WHERE user_id=:uid AND table_id=:tid", {"uid":actor["id"],"tid":table_id}))


def lock_table(db, table_id):
    suffix = " FOR UPDATE" if db.bind.dialect.name == "postgresql" else ""
    db.execute(text("SELECT id FROM polling_tables WHERE id=:id" + suffix), {"id": table_id})


class Login(BaseModel):
    user_id: int
    code: str


@app.post("/api/dev/login")
def login(body: Login, response: Response, db: Session = Depends(db_session)):
    if settings.app_env != "development" or body.code != "TEST-ONLY-2026":
        fail(401, "Código de prueba inválido")
    actor = one(db, "SELECT * FROM users WHERE id=:id AND active=true AND synthetic=true", {"id":body.user_id})
    if not actor:
        fail(401, "Usuario de prueba inválido")
    token = secrets.token_urlsafe(32)
    db.execute(text("INSERT INTO sessions(id,user_id,expires_at) VALUES (:id,:uid,:expires)"), {"id":hashlib.sha256(token.encode()).hexdigest(),"uid":actor["id"],"expires":now()+timedelta(hours=8)})
    db.commit()
    response.set_cookie("actas_session",token,httponly=True,samesite="strict",secure=False,max_age=28800)
    return {"name":actor["display_name"],"role":actor["role"],"synthetic":True}


@app.post("/api/logout")
def logout(response: Response, request: Request, actor=Depends(user), db: Session=Depends(db_session)):
    token = request.cookies.get("actas_session")
    db.execute(text("UPDATE sessions SET revoked_at=:now WHERE id=:id"), {"now":now(),"id":hashlib.sha256(token.encode()).hexdigest()})
    db.commit()
    response.delete_cookie("actas_session")
    return {"ok":True}


@app.get("/api/me")
def me(actor=Depends(user)):
    return {"id":actor["id"],"name":actor["display_name"],"role":actor["role"],"can_view_results":actor["can_view_results"],"synthetic":actor["synthetic"]}


@app.get("/api/tables")
def tables(actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] == "administrador":
        return all_rows(db,"SELECT * FROM polling_tables ORDER BY id LIMIT 100")
    return all_rows(db,"SELECT t.* FROM polling_tables t JOIN assignments a ON a.table_id=t.id WHERE a.user_id=:uid ORDER BY t.id",{"uid":actor["id"]})


@app.get("/api/candidacies")
def candidacies(table_id: int, election_id: int = 1, actor=Depends(user), db: Session=Depends(db_session)):
    if not can_access(db, actor, table_id):
        fail()
    table = one(db, "SELECT province_code FROM polling_tables WHERE id=:id", {"id": table_id})
    if not table:
        fail(404, "Mesa inexistente")
    active = one(db, "SELECT id FROM candidacy_imports WHERE election_id=:eid AND chamber='congreso' AND status='active'", {"eid": election_id})
    if active:
        return all_rows(db, "SELECT c.id,c.name,r.candidacy_code AS code FROM candidacy_import_rows r JOIN candidacies c ON c.id=r.candidacy_id WHERE r.import_id=:iid AND r.constituency_code=:province ORDER BY r.candidacy_code", {"iid": active["id"], "province": table["province_code"]})
    return all_rows(db, "SELECT id,name FROM candidacies WHERE election_id=:eid AND chamber='congreso' AND constituency_code=:province ORDER BY id", {"eid": election_id, "province": table["province_code"]})


class NewDocument(BaseModel):
    table_id: int
    election_id: int = 1
    chamber: Literal["congreso", "senado"] = "congreso"
    document_type: Literal["escrutinio"] = "escrutinio"
    mime_type: Literal["image/jpeg", "image/png"]
    idempotency_key: str = Field(min_length=8,max_length=100)


@app.post("/api/documents")
def create_document(body: NewDocument, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("apoderado","supervisor","administrador") or not can_access(db,actor,body.table_id):
        fail()
    existing = one(db,"SELECT d.*,i.object_key,i.mime_type FROM documents d JOIN document_images i ON i.document_id=d.id WHERE d.uploader_id=:uid AND d.idempotency_key=:key",{"uid":actor["id"],"key":body.idempotency_key})
    if existing:
        if (existing["table_id"],existing["election_id"],existing["chamber"],existing["document_type"],existing["mime_type"]) != (body.table_id,body.election_id,body.chamber,body.document_type,body.mime_type):
            fail(409,"Clave de idempotencia usada para otro documento")
        return {"id":existing["id"],"upload_url":upload_url(existing["object_key"],body.mime_type) if existing["status"]=="pending_upload" else None,"status":existing["status"]}
    if not one(db,"SELECT 1 AS ok FROM elections WHERE id=:id",{"id":body.election_id}):
        fail(404,"Elección inexistente")
    if not one(db,"SELECT 1 AS ok FROM election_document_types dt JOIN election_chambers ec ON ec.election_id=dt.election_id AND ec.chamber=dt.chamber WHERE dt.election_id=:eid AND dt.chamber=:ch AND dt.document_type=:typ AND dt.enabled=true AND ec.enabled=true",{"eid":body.election_id,"ch":body.chamber,"typ":body.document_type}):
        fail(422,"Cámara o tipo documental no habilitado para esta elección")
    active_catalog = one(db,"SELECT id FROM catalog_imports WHERE election_id=:eid AND status='active'",{"eid":body.election_id})
    if active_catalog and not one(db,"SELECT 1 AS ok FROM catalog_rows WHERE import_id=:iid AND table_id=:tid",{"iid":active_catalog["id"],"tid":body.table_id}):
        fail(422,"Mesa fuera del catálogo electoral activo")
    did, iid = str(uuid.uuid4()), str(uuid.uuid4())
    key = f"elections/{body.election_id}/documents/{did}/original"
    # Lock the table so concurrent versions receive distinct sequence numbers.
    lock_table(db,body.table_id)
    version = db.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM documents WHERE election_id=:eid AND table_id=:tid AND chamber=:ch AND document_type=:typ"),{"eid":body.election_id,"tid":body.table_id,"ch":body.chamber,"typ":body.document_type}).scalar_one()
    db.execute(text("INSERT INTO documents(id,election_id,table_id,chamber,document_type,version,status,uploader_id,idempotency_key) VALUES (:id,:eid,:tid,:ch,:typ,:version,'pending_upload',:uid,:idem)"),{"id":did,"eid":body.election_id,"tid":body.table_id,"ch":body.chamber,"typ":body.document_type,"version":version,"uid":actor["id"],"idem":body.idempotency_key})
    db.execute(text("INSERT INTO document_images(id,document_id,object_key,mime_type) VALUES (:id,:did,:key,:mime)"),{"id":iid,"did":did,"key":key,"mime":body.mime_type})
    db.commit()
    return {"id":did,"version":version,"upload_url":upload_url(key,body.mime_type),"status":"pending_upload"}


def owned_document(db,actor,did):
    d = one(db,"SELECT * FROM documents WHERE id=:id",{"id":did})
    if not d:
        fail(404,"Documento inexistente")
    if actor["role"] == "organizacion" and actor["can_view_results"]:
        return d
    if not can_access(db,actor,d["table_id"]):
        fail()
    return d


@app.post("/api/documents/{did}/complete")
def complete(did: str, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("apoderado", "supervisor", "administrador"):
        fail()
    d = owned_document(db,actor,did)
    if actor["role"] == "apoderado" and d["uploader_id"] != actor["id"]:
        fail()
    if d["status"] != "pending_upload":
        return {"status":d["status"]}
    im = one(db,"SELECT * FROM document_images WHERE document_id=:id",{"id":did})
    try:
        data = get_object(im["object_key"])
    except Exception:
        fail(400,"Imagen no recibida")
    if not data or len(data)>settings.max_image_bytes:
        fail(400,"Tamaño de imagen inválido")
    try:
        picture = Image.open(io.BytesIO(data))
        width,height=picture.size
        orientation=picture.getexif().get(274,1)
        picture.verify()
        fmt = picture.format
    except Exception:
        fail(400,"Imagen ilegible")
    if fmt not in ("JPEG","PNG") or im["mime_type"] != {"JPEG":"image/jpeg","PNG":"image/png"}[fmt]:
        fail(400,"Formato de imagen no coincide")
    if width<32 or height<32 or orientation not in range(1,9):
        fail(400,"Dimensiones u orientación inválidas")
    evidence_key=f"elections/{d['election_id']}/documents/{did}/evidence/{hashlib.sha256(data).hexdigest()}"
    put_evidence(evidence_key,data,im["mime_type"])
    sealed=get_object(evidence_key)
    if hashlib.sha256(sealed).hexdigest()!=hashlib.sha256(data).hexdigest():
        fail(409,"La imagen cambió durante la confirmación; reintenta")
    db.execute(text("UPDATE document_images SET object_key=:evidence,byte_size=:size,sha256=:sha,width_px=:width,height_px=:height,exif_orientation=:orientation,received_at=:now WHERE document_id=:id"),{"evidence":evidence_key,"size":len(data),"sha":hashlib.sha256(data).hexdigest(),"width":width,"height":height,"orientation":orientation,"now":now(),"id":did})
    db.execute(text("UPDATE documents SET status='received',updated_at=:now WHERE id=:id"),{"now":now(),"id":did})
    db.execute(text("INSERT INTO processing_jobs(id,document_id,status) VALUES (:id,:did,'queued') ON CONFLICT(document_id) DO NOTHING"),{"id":str(uuid.uuid4()),"did":did})
    db.commit()
    try:
        delete_staging(im["object_key"])
    except Exception:
        pass  # Sealed evidence remains; stale staging objects can be cleaned later.
    return {"status":"received","sha256":hashlib.sha256(data).hexdigest()}


@app.get("/api/documents")
def documents(limit: int=20, offset: int=0, actor=Depends(user), db: Session=Depends(db_session)):
    if not 1<=limit<=100 or offset<0: fail(422,"Paginación inválida")
    if actor["role"] in ("administrador", "organizacion") and (actor["role"] == "administrador" or actor["can_view_results"]):
        return all_rows(db,"SELECT id,table_id,version,status,conflict,created_at FROM documents ORDER BY created_at DESC,id DESC LIMIT :lim OFFSET :off",{"lim":limit,"off":offset})
    return all_rows(db,"SELECT d.id,d.table_id,d.version,d.status,d.conflict,d.created_at FROM documents d JOIN assignments a ON a.table_id=d.table_id WHERE a.user_id=:uid ORDER BY d.created_at DESC,d.id DESC LIMIT :lim OFFSET :off",{"uid":actor["id"],"lim":limit,"off":offset})


@app.get("/api/documents/{did}")
def document(did: str, actor=Depends(user), db: Session=Depends(db_session)):
    d = owned_document(db,actor,did)
    extraction = one(db,"SELECT provider,model_version,raw_json FROM extractions WHERE document_id=:id ORDER BY created_at DESC LIMIT 1",{"id":did})
    review_row = one(db,"SELECT r.values_json,r.decision,r.created_at,u.display_name AS reviewer FROM reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.document_id=:id ORDER BY r.created_at DESC LIMIT 1",{"id":did})
    if review_row:
        review_row["values"] = json.loads(review_row.pop("values_json"))
    return {"id":did,"election_id":d["election_id"],"table_id":d["table_id"],"version":d["version"],"status":d["status"],"conflict":d["conflict"],"current_validated":d["current_validated"],"review":review_row,"extraction":extraction}


@app.get("/api/documents/{did}/image")
def image_url(did: str, actor=Depends(user), db: Session=Depends(db_session)):
    owned_document(db,actor,did)
    im = one(db,"SELECT object_key,mime_type,received_at FROM document_images WHERE document_id=:id",{"id":did})
    if not im or not im["received_at"]: fail(404,"Imagen no recibida")
    return {"url":read_url(im["object_key"],im["mime_type"]),"expires_seconds":120}


class Review(BaseModel):
    decision: Literal["validated","rejected"]
    mesa_congreso_confirmed: StrictBool = False
    votes: dict[str, StrictInt] = Field(default_factory=dict)
    candidate_votes: dict[str, StrictInt] = Field(default_factory=dict)
    blank: StrictInt = 0
    null: StrictInt = 0
    total: StrictInt = 0

    model_config = {"extra": "forbid"}


@app.post("/api/documents/{did}/review")
def review(did: str, body: Review, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("apoderado","supervisor","administrador"): fail()
    d = owned_document(db,actor,did)
    if actor["role"] == "apoderado" and d["uploader_id"] != actor["id"]:
        fail()
    if d["status"] not in ("pending_review","validated","rejected"):
        fail(409,"Documento aún no revisable")
    if d["status"] in ("validated","rejected"):
        fail(409,"Documento ya revisado")
    if any(v<0 for v in [*body.votes.values(),*body.candidate_votes.values(),body.blank,body.null,body.total]): fail(422,"Votos negativos")
    active_candidacies = one(db, "SELECT id FROM candidacy_imports WHERE election_id=:eid AND chamber='congreso' AND status='active'", {"eid": d["election_id"]}) if d["chamber"] == "congreso" else None
    if active_candidacies:
        expected = {str(r["id"]) for r in all_rows(db, "SELECT r.candidacy_id AS id FROM candidacy_import_rows r WHERE r.import_id=:iid AND r.constituency_code=(SELECT province_code FROM polling_tables WHERE id=:tid)", {"iid": active_candidacies["id"], "tid": d["table_id"]})}
    else:
        expected = {str(r["id"]) for r in all_rows(db,"SELECT id FROM candidacies WHERE election_id=:eid AND chamber=:ch AND constituency_code=(SELECT province_code FROM polling_tables WHERE id=:tid)",{"eid":d["election_id"],"ch":d["chamber"],"tid":d["table_id"]})}
    if body.decision == "validated":
        if d["chamber"] == "congreso":
            if not body.mesa_congreso_confirmed:
                fail(422,"Confirma que la imagen es un acta de escrutinio de mesa para Congreso")
            if not expected or body.candidate_votes or set(body.votes)!=expected or sum(body.votes.values())+body.blank+body.null!=body.total:
                fail(422,"Candidaturas incompletas o suma inconsistente para Congreso")
        else:
            candidates = {str(r["id"]) for r in all_rows(db,"SELECT ca.id FROM candidates ca JOIN candidacies c ON c.id=ca.candidacy_id WHERE c.election_id=:eid AND c.chamber='senado' AND c.constituency_code=(SELECT province_code FROM polling_tables WHERE id=:tid)",{"eid":d["election_id"],"tid":d["table_id"]})}
            if body.votes or not candidates or set(body.candidate_votes)!=candidates or body.blank+body.null>body.total or any(v>body.total for v in body.candidate_votes.values()):
                fail(422,"Votos por candidato incompletos o inválidos para Senado")
    # Rejecting stores the review, but never updates results.
    lock_table(db,d["table_id"])
    prior = one(db,"SELECT id FROM documents WHERE election_id=:eid AND table_id=:tid AND chamber=:ch AND document_type=:typ AND current_validated=true",{"eid":d["election_id"],"tid":d["table_id"],"ch":d["chamber"],"typ":d["document_type"]})
    prior_values = None
    if prior:
        rr = one(db,"SELECT values_json FROM reviews WHERE document_id=:id AND decision='validated' ORDER BY created_at DESC LIMIT 1",{"id":prior["id"]})
        prior_values = json.loads(rr["values_json"]) if rr else None
    values = body.model_dump()
    conflict = body.decision == "validated" and prior_values is not None and {k:values[k] for k in ("votes","candidate_votes","blank","null","total")} != {k:prior_values.get(k,{}) for k in ("votes","candidate_votes","blank","null","total")}
    db.execute(text("INSERT INTO reviews(id,document_id,reviewer_id,values_json,decision) VALUES (:id,:did,:uid,:values,:decision)"),{"id":str(uuid.uuid4()),"did":did,"uid":actor["id"],"values":json.dumps(values),"decision":body.decision})
    if body.decision == "validated":
        if conflict:
            db.execute(text("INSERT INTO conflict_resolutions(document_id,incumbent_id,status) VALUES (:did,:prior,'pending')"),{"did":did,"prior":prior["id"]})
        for cid,votes in body.votes.items():
            db.execute(text("INSERT INTO document_votes(document_id,candidacy_id,votes) VALUES (:did,:cid,:votes)"),{"did":did,"cid":int(cid),"votes":votes})
        for cid,votes in body.candidate_votes.items():
            db.execute(text("INSERT INTO candidate_votes(document_id,candidate_id,votes) VALUES (:did,:cid,:votes)"),{"did":did,"cid":int(cid),"votes":votes})
    current = body.decision == "validated" and prior is None
    db.execute(text("UPDATE documents SET status=:status,current_validated=:current,conflict=:conflict,blank_votes=:blank,null_votes=:null,total_votes=:total,updated_at=:now WHERE id=:id"),{"status":body.decision,"current":current,"conflict":conflict,"blank":body.blank if body.decision=="validated" else None,"null":body.null if body.decision=="validated" else None,"total":body.total if body.decision=="validated" else None,"now":now(),"id":did})
    db.execute(text("INSERT INTO audit_events(id,document_id,actor_id,action,details_json) VALUES (:id,:did,:uid,:action,:details)"),{"id":str(uuid.uuid4()),"did":did,"uid":actor["id"],"action":body.decision,"details":json.dumps({"conflict":conflict,"replaced_document_id":prior["id"] if prior and body.decision=="validated" else None})})
    db.commit()
    return {"status":body.decision,"conflict":conflict,"resolution_pending":conflict,"current_validated":current,"incumbent_document_id":prior["id"] if prior else None}


@app.get("/api/conflicts")
def conflicts(limit: int=20, offset: int=0, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("organizacion", "administrador") or not actor["can_view_results"]:
        fail()
    if not 1<=limit<=100 or offset<0: fail(422,"Paginación inválida")
    return all_rows(db,"SELECT r.document_id,r.incumbent_id,r.created_at,d.table_id,d.election_id,d.chamber,d.document_type FROM conflict_resolutions r JOIN documents d ON d.id=r.document_id WHERE r.status='pending' ORDER BY r.created_at,r.document_id LIMIT :lim OFFSET :off",{"lim":limit,"off":offset})


class ConflictDecision(BaseModel):
    decision: Literal["accept_new", "keep_incumbent"]
    reason: str = Field(min_length=3,max_length=1000)


@app.post("/api/conflicts/{did}/resolve")
def resolve_conflict(did: str, body: ConflictDecision, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("organizacion", "administrador") or not actor["can_view_results"]:
        fail()
    d = one(db,"SELECT * FROM documents WHERE id=:id",{"id":did})
    if not d:
        fail(404,"Documento inexistente")
    lock_table(db,d["table_id"])
    resolution = one(db,"SELECT * FROM conflict_resolutions WHERE document_id=:id AND status='pending'",{"id":did})
    if not resolution:
        fail(409,"No hay discrepancia pendiente")
    incumbent = one(db,"SELECT id FROM documents WHERE election_id=:eid AND table_id=:tid AND chamber=:ch AND document_type=:typ AND current_validated=true",{"eid":d["election_id"],"tid":d["table_id"],"ch":d["chamber"],"typ":d["document_type"]})
    if not incumbent or incumbent["id"] != resolution["incumbent_id"]:
        fail(409,"La versión vigente ha cambiado; revisar de nuevo")
    if body.decision == "accept_new":
        db.execute(text("UPDATE documents SET current_validated=false,updated_at=:now WHERE id=:id"),{"id":incumbent["id"],"now":now()})
        db.execute(text("UPDATE documents SET current_validated=true,updated_at=:now WHERE id=:id"),{"id":did,"now":now()})
    db.execute(text("UPDATE conflict_resolutions SET status=:status,resolver_id=:uid,reason=:reason,resolved_at=:now WHERE document_id=:id"),{"status":"accepted" if body.decision=="accept_new" else "kept_incumbent","uid":actor["id"],"reason":body.reason,"now":now(),"id":did})
    db.execute(text("INSERT INTO audit_events(id,document_id,actor_id,action,details_json) VALUES (:id,:did,:uid,'resolve_conflict',:details)"),{"id":str(uuid.uuid4()),"did":did,"uid":actor["id"],"details":json.dumps(body.model_dump())})
    db.commit()
    return {"decision":body.decision,"current_document_id":did if body.decision=="accept_new" else incumbent["id"]}


@app.post("/api/documents/{did}/withdraw")
def withdraw(did: str, actor=Depends(user), db: Session=Depends(db_session)):
    if actor["role"] not in ("supervisor","administrador"): fail()
    d=owned_document(db,actor,did)
    if d["status"]!="validated" or not d["current_validated"]: fail(409,"No es versión vigente validada")
    lock_table(db,d["table_id"])
    db.execute(text("UPDATE documents SET status='rejected',current_validated=false,updated_at=:now WHERE id=:id"),{"id":did,"now":now()})
    db.execute(text("INSERT INTO audit_events(id,document_id,actor_id,action,details_json) VALUES (:id,:did,:uid,'withdraw',:details)"),{"id":str(uuid.uuid4()),"did":did,"uid":actor["id"],"details":json.dumps({"prior_status":"validated"})})
    db.commit()
    return {"status":"rejected","withdrawn":True}


@app.get("/api/dashboard")
def dashboard(election_id: int=1, chamber: Literal["congreso","senado"]="congreso", actor=Depends(user), db: Session=Depends(db_session)):
    if not actor["can_view_results"]: fail()
    if not one(db,"SELECT 1 AS ok FROM election_chambers WHERE election_id=:eid AND chamber=:ch AND enabled=true",{"eid":election_id,"ch":chamber}):
        fail(404,"Cámara no habilitada para esta elección")
    active_catalog=one(db,"SELECT id,version FROM catalog_imports WHERE election_id=:eid AND status='active'",{"eid":election_id})
    scope = "" if actor["role"] in ("organizacion","administrador") else " AND EXISTS (SELECT 1 FROM assignments a WHERE a.table_id=d.table_id AND a.user_id=:uid)"
    if active_catalog:
        scope += " AND EXISTS (SELECT 1 FROM catalog_rows cr WHERE cr.import_id=:iid AND cr.table_id=d.table_id)"
    params={"uid":actor["id"],"eid":election_id,"ch":chamber}
    if active_catalog:
        params["iid"] = active_catalog["id"]
    base="d.election_id=:eid AND d.chamber=:ch"
    states=all_rows(db,"SELECT d.status,COUNT(*) AS count FROM documents d WHERE "+base+scope+" GROUP BY d.status",params)
    votes=all_rows(db,"SELECT c.id,c.name,SUM(v.votes) AS votes FROM document_votes v JOIN documents d ON d.id=v.document_id JOIN candidacies c ON c.id=v.candidacy_id WHERE d.current_validated=true AND d.status='validated' AND "+base+scope+" GROUP BY c.id,c.name ORDER BY c.name",params)
    candidate_votes=all_rows(db,"SELECT ca.id,ca.name,SUM(v.votes) AS votes FROM candidate_votes v JOIN documents d ON d.id=v.document_id JOIN candidates ca ON ca.id=v.candidate_id WHERE d.current_validated=true AND d.status='validated' AND "+base+scope+" GROUP BY ca.id,ca.name ORDER BY ca.name",params)
    count=db.execute(text("SELECT COUNT(*) FROM documents d WHERE d.current_validated=true AND d.status='validated' AND "+base+scope),params).scalar_one()
    sums=one(db,"SELECT COALESCE(SUM(d.blank_votes),0) AS blank_votes,COALESCE(SUM(d.null_votes),0) AS null_votes,COALESCE(SUM(d.total_votes),0) AS total_votes FROM documents d WHERE d.current_validated=true AND d.status='validated' AND "+base+scope,params)
    covered=db.execute(text("SELECT COUNT(DISTINCT d.table_id) FROM documents d WHERE d.current_validated=true AND d.status='validated' AND "+base+scope),params).scalar_one()
    if active_catalog:
        denominator=db.execute(text("SELECT COUNT(*) FROM catalog_rows cr WHERE cr.import_id=:iid"+("" if actor["role"] in ("organizacion","administrador") else " AND EXISTS (SELECT 1 FROM assignments a WHERE a.table_id=cr.table_id AND a.user_id=:uid)")),{"iid":active_catalog["id"],"uid":actor["id"]}).scalar_one()
    else:
        denominator=db.execute(text("SELECT COUNT(*) FROM polling_tables" if actor["role"] in ("organizacion","administrador") else "SELECT COUNT(*) FROM assignments WHERE user_id=:uid"),params).scalar_one()
    election=one(db,"SELECT name,synthetic FROM elections WHERE id=:eid",params)
    return {"election_id":election_id,"election_name":election["name"],"chamber":chamber,"synthetic":election["synthetic"],"catalog_version":active_catalog["version"] if active_catalog else None,"updated_at":now().isoformat()+"Z","validated_documents":count,"covered_tables":covered,"assigned_tables_denominator":denominator,"totals":sums,"states":states,"votes":votes,"candidate_votes":candidate_votes}


@app.get("/")
def home():
    return FileResponse("app/static/index.html")
