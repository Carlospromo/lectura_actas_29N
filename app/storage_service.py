"""Private, persistent development object service. Never enabled in production."""
import hmac
import os
import time
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.storage import signature

app=FastAPI(title="Development private object store")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:8000"],allow_methods=["PUT","GET"],allow_headers=["Content-Type"])
ROOT=Path(settings.storage_root).resolve()


def target(key):
    if not key or any(part in ("", ".", "..") for part in key.split("/")):
        raise HTTPException(400,"Invalid object key")
    path=(ROOT/key).resolve()
    if not path.is_relative_to(ROOT):
        raise HTTPException(400,"Invalid object key")
    return path


def signed(request,key,method):
    q=request.query_params
    try:
        expires=int(q["expires"])
        mime=q["mime"]
        sig=q["sig"]
    except (KeyError,ValueError):
        raise HTTPException(403,"Missing upload permission")
    if expires<time.time() or expires>time.time()+601 or mime not in ("image/jpeg","image/png"):
        raise HTTPException(403,"Expired or invalid permission")
    if not hmac.compare_digest(signature(method,key,expires,mime),sig):
        raise HTTPException(403,"Invalid permission")
    return mime


def internal(request):
    secret=request.headers.get("X-Storage-Secret","")
    if not hmac.compare_digest(secret,settings.storage_secret):
        raise HTTPException(403,"Private storage")


async def bounded_body(request):
    chunks=[]
    size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>settings.max_image_bytes:
            raise HTTPException(413,"Object too large")
        chunks.append(chunk)
    return b"".join(chunks)


def durable_write(path,data,exclusive=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f".tmp-{os.getpid()}-{time.time_ns()}")
    with open(temp,"xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if exclusive and path.exists():
        temp.unlink()
        if path.read_bytes()!=data:
            raise HTTPException(409,"Evidence already exists with different content")
        return
    os.replace(temp,path)


@app.get("/health")
def health():
    ROOT.mkdir(parents=True,exist_ok=True)
    return {"ok":True}


@app.put("/objects/{key:path}")
async def put_signed(key: str,request: Request):
    mime=signed(request,key,"PUT")
    if not key.endswith("/original") or request.headers.get("content-type")!=mime:
        raise HTTPException(403,"Upload target or type not allowed")
    durable_write(target(key),await bounded_body(request))
    return {"ok":True}


@app.get("/objects/{key:path}")
def get_signed(key: str,request: Request):
    mime=signed(request,key,"GET")
    path=target(key)
    if not path.is_file(): raise HTTPException(404,"Object not found")
    return Response(path.read_bytes(),media_type=mime,headers={"Cache-Control":"private, no-store"})


@app.get("/internal/objects/{key:path}")
def get_internal(key: str,request: Request):
    internal(request)
    path=target(key)
    if not path.is_file(): raise HTTPException(404,"Object not found")
    return Response(path.read_bytes(),media_type="application/octet-stream")


@app.put("/internal/objects/{key:path}")
async def put_internal(key: str,request: Request):
    internal(request)
    if "/evidence/" not in key: raise HTTPException(403,"Evidence only")
    durable_write(target(key),await bounded_body(request),exclusive=True)
    return {"ok":True}


@app.delete("/internal/objects/{key:path}")
def delete_internal(key: str,request: Request):
    internal(request)
    if not key.endswith("/original"): raise HTTPException(403,"Staging only")
    target(key).unlink(missing_ok=True)
    return {"ok":True}
