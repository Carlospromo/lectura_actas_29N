import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.config import settings


def client(public=False):
    return boto3.client("s3", endpoint_url=settings.s3_public_endpoint if public else settings.s3_endpoint,
                        aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
                        region_name="us-east-1", config=Config(signature_version="s3v4"))


def ensure_bucket():
    s3 = client()
    try:
        s3.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        s3.create_bucket(Bucket=settings.s3_bucket)


def upload_url(key, mime):
    return client(public=True).generate_presigned_url("put_object", Params={"Bucket":settings.s3_bucket,"Key":key,"ContentType":mime}, ExpiresIn=600)


def read_url(key):
    return client(public=True).generate_presigned_url("get_object", Params={"Bucket":settings.s3_bucket,"Key":key}, ExpiresIn=120)
