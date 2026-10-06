import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .pricing import STORAGE_CLASSES
from .optimizer import analyze_bucket
from .mock_data import generate_bucket

app = FastAPI(
    title="S3 Storage Class Lifecycle Cost Optimizer",
    description="Analyzes S3 object access patterns and recommends storage-class transitions to cut monthly storage cost.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache of the last generated/fetched bucket so /analyze can
# reuse it without re-hitting AWS or re-rolling random demo data.
_LAST_BUCKET = {}


def _aws_available():
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))


@app.get("/api/health")
def health():
    return {"status": "ok", "aws_configured": _aws_available(), "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/pricing")
def pricing():
    return STORAGE_CLASSES


@app.get("/api/buckets")
def list_buckets():
    """Lists real S3 buckets if AWS credentials are configured, otherwise
    returns a single demo bucket so the UI always has something to select."""
    if _aws_available():
        try:
            import boto3
            s3 = boto3.client("s3")
            resp = s3.list_buckets()
            return {"source": "aws", "buckets": [b["Name"] for b in resp.get("Buckets", [])]}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AWS error: {e}")
    return {"source": "demo", "buckets": ["demo-analytics-bucket"]}


def _fetch_real_bucket(bucket_name: str):
    import boto3
    s3 = boto3.client("s3")
    cw = boto3.client("cloudwatch")
    paginator = s3.get_paginator("list_objects_v2")
    now = datetime.now(timezone.utc)
    objects = []
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            age_days = (now - obj["LastModified"]).days
            objects.append({
                "key": obj["Key"],
                "size_kb": obj["Size"] / 1024,
                "storage_class": obj.get("StorageClass", "STANDARD"),
                "last_modified": obj["LastModified"].isoformat(),
                "age_days": age_days,
                # Real access-frequency data requires S3 Server Access Logs
                # or S3 Storage Lens activity metrics enabled on the bucket;
                # default to "unknown -> treat as cold" until wired up.
                "last_accessed_days_ago": age_days,
                "access_count_30d": 0,
            })
    return {"bucket": bucket_name, "region": s3.meta.region_name, "objects": objects}


@app.get("/api/simulate")
def simulate(bucket_name: str = Query("demo-analytics-bucket"), num_objects: int = Query(220, ge=10, le=2000), seed: int | None = None):
    """Generates fresh synthetic bucket data for the demo/no-AWS-account path."""
    data = generate_bucket(bucket_name, num_objects, seed)
    _LAST_BUCKET[bucket_name] = data
    return {"bucket": bucket_name, "object_count": len(data["objects"])}


@app.get("/api/analyze/{bucket_name}")
def analyze(bucket_name: str, use_live_aws: bool = Query(False)):
    if use_live_aws and _aws_available():
        try:
            data = _fetch_real_bucket(bucket_name)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AWS error: {e}")
    elif bucket_name in _LAST_BUCKET:
        data = _LAST_BUCKET[bucket_name]
    else:
        data = generate_bucket(bucket_name)
        _LAST_BUCKET[bucket_name] = data

    return analyze_bucket(data)


class LifecyclePolicyRequest(BaseModel):
    bucket_name: str


@app.post("/api/lifecycle-policy")
def generate_lifecycle_policy(req: LifecyclePolicyRequest):
    """Turns the recommendation set into an AWS S3 Lifecycle Configuration
    JSON the user can apply with `aws s3api put-bucket-lifecycle-configuration`."""
    if req.bucket_name not in _LAST_BUCKET:
        raise HTTPException(status_code=404, detail="Run /api/analyze first for this bucket.")

    analyzed = analyze_bucket(_LAST_BUCKET[req.bucket_name])
    transitions_by_prefix = {}
    class_map = {
        "STANDARD_IA": "STANDARD_IA",
        "ONEZONE_IA": "ONEZONE_IA",
        "GLACIER_IR": "GLACIER_IR",
        "GLACIER_FR": "GLACIER",
        "DEEP_ARCHIVE": "DEEP_ARCHIVE",
    }
    thresholds = {"STANDARD_IA": 30, "ONEZONE_IA": 30, "GLACIER_IR": 60, "GLACIER_FR": 90, "DEEP_ARCHIVE": 180}

    for obj in analyzed["objects"]:
        rec = obj["recommended_class"]
        if rec == "STANDARD":
            continue
        prefix = obj["key"].rsplit("/", 1)[0] + "/" if "/" in obj["key"] else ""
        transitions_by_prefix.setdefault(prefix, set()).add(rec)

    rules = []
    for prefix, classes in transitions_by_prefix.items():
        transitions = sorted(
            ({"Days": thresholds[c], "StorageClass": class_map[c]} for c in classes),
            key=lambda t: t["Days"],
        )
        rules.append({
            "ID": f"optimize-{prefix or 'root'}".replace("/", "-").strip("-"),
            "Filter": {"Prefix": prefix},
            "Status": "Enabled",
            "Transitions": transitions,
        })

    return {"Rules": rules}
