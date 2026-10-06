"""
Generates a believable synthetic bucket so the dashboard can be demoed
without real AWS credentials. Each object gets a random size, an age
(days since last modified) and an access pattern (days since last
accessed + how many times it's been accessed in the last 30 days),
mimicking what CloudWatch S3 Storage Lens / access logs would give you.
"""
import random
from datetime import datetime, timedelta

FOLDERS = [
    "logs/app-server", "logs/access", "backups/db-snapshots",
    "media/uploads", "media/thumbnails", "reports/monthly",
    "reports/archived", "datasets/raw", "datasets/processed", "exports/csv",
]

EXTENSIONS = [".log", ".json", ".csv", ".png", ".jpg", ".sql.gz", ".parquet", ".pdf"]


def generate_bucket(bucket_name: str = "demo-analytics-bucket", num_objects: int = 220, seed: int | None = None):
    rng = random.Random(seed)
    now = datetime.utcnow()
    objects = []

    for i in range(num_objects):
        folder = rng.choice(FOLDERS)
        ext = rng.choice(EXTENSIONS)
        key = f"{folder}/{rng.randint(1000, 9999)}{ext}"

        # Bias ages so the demo has a realistic long-tail: lots of recent
        # objects, fewer old ones, some very old (classic backup pattern).
        age_days = int(rng.betavariate(1.6, 4.0) * 900)
        size_kb = round(rng.lognormvariate(6.5, 2.0), 1)  # skewed size distribution
        size_kb = max(1.0, min(size_kb, 5_000_000))  # cap at ~5GB objects

        # Access pattern: newer objects accessed more often & more recently.
        if age_days < 30:
            last_accessed_days_ago = rng.randint(0, min(age_days, 10))
            access_count_30d = rng.randint(3, 60)
        elif age_days < 120:
            last_accessed_days_ago = rng.randint(0, 60)
            access_count_30d = rng.randint(0, 10)
        else:
            last_accessed_days_ago = rng.randint(30, age_days)
            access_count_30d = rng.choice([0, 0, 0, 0, 1, 2])

        last_modified = now - timedelta(days=age_days)

        objects.append({
            "key": key,
            "size_kb": size_kb,
            "storage_class": "STANDARD",
            "last_modified": last_modified.isoformat() + "Z",
            "age_days": age_days,
            "last_accessed_days_ago": last_accessed_days_ago,
            "access_count_30d": access_count_30d,
        })

    return {"bucket": bucket_name, "region": "us-east-1", "objects": objects}
