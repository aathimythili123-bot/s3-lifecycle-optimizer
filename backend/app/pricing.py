"""
S3 storage class pricing (USD / GB / month, us-east-1 list prices) and the
retrieval + minimum-duration penalties used by the optimizer.

Prices are approximate public list prices and are kept in one place so they
are easy to update without touching the optimization logic.
"""

STORAGE_CLASSES = {
    "STANDARD": {
        "label": "S3 Standard",
        "price_per_gb": 0.023,
        "retrieval_per_gb": 0.0,
        "min_duration_days": 0,
        "min_object_size_kb": 0,
    },
    "STANDARD_IA": {
        "label": "Standard-Infrequent Access",
        "price_per_gb": 0.0125,
        "retrieval_per_gb": 0.01,
        "min_duration_days": 30,
        "min_object_size_kb": 128,
    },
    "ONEZONE_IA": {
        "label": "One Zone-Infrequent Access",
        "price_per_gb": 0.01,
        "retrieval_per_gb": 0.01,
        "min_duration_days": 30,
        "min_object_size_kb": 128,
    },
    "GLACIER_IR": {
        "label": "Glacier Instant Retrieval",
        "price_per_gb": 0.004,
        "retrieval_per_gb": 0.03,
        "min_duration_days": 90,
        "min_object_size_kb": 128,
    },
    "GLACIER_FR": {
        "label": "Glacier Flexible Retrieval",
        "price_per_gb": 0.0036,
        "retrieval_per_gb": 0.02,
        "min_duration_days": 90,
        "min_object_size_kb": 0,
    },
    "DEEP_ARCHIVE": {
        "label": "Glacier Deep Archive",
        "price_per_gb": 0.00099,
        "retrieval_per_gb": 0.02,
        "min_duration_days": 180,
        "min_object_size_kb": 0,
    },
}

# Ordered coldest-to-warmest is not needed; ordered by rule evaluation below.
RULE_ORDER = ["DEEP_ARCHIVE", "GLACIER_FR", "GLACIER_IR", "STANDARD_IA", "ONEZONE_IA", "STANDARD"]
