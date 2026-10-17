"""Development storage adapter; replace with Cloud Storage signed URLs for production."""
import hashlib
import hmac
import time
from urllib.parse import quote
import httpx
from app.config import settings


def signature(method: str, key: str, expires: int, mime: str):
    msg=f"{method}\n{key}\n{expires}\n{mime}".encode()
    return hmac.new(settings.storage_secret.encode(),msg,hashlib.sha256).hexdigest()


def signed_url(method: str, key: str, mime: str, seconds: int):
    expires=int(time.time())+seconds
    sig=signature(method,key,expires,mime)
    return f"{settings.storage_public_endpoint}/objects/{quote(key,safe='/')}?expires={expires}&mime={quote(mime,safe='')}&sig={sig}"


def upload_url(key, mime):
    return signed_url("PUT",key,mime,600)


def read_url(key, mime="image/jpeg"):
    return signed_url("GET",key,mime,120)


def get_object(key):
    r=httpx.get(f"{settings.storage_endpoint}/internal/objects/{key}",headers={"X-Storage-Secret":settings.storage_secret},timeout=30)
    r.raise_for_status()
    return r.content


def put_evidence(key, data, mime):
    r=httpx.put(f"{settings.storage_endpoint}/internal/objects/{key}",headers={"X-Storage-Secret":settings.storage_secret,"Content-Type":mime},content=data,timeout=30)
    r.raise_for_status()


def delete_staging(key):
    r=httpx.delete(f"{settings.storage_endpoint}/internal/objects/{key}",headers={"X-Storage-Secret":settings.storage_secret},timeout=10)
    r.raise_for_status()
