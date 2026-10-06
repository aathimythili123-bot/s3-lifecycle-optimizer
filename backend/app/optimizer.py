"""
Core optimization engine: for each object, decide the cheapest storage
class that still respects AWS's minimum-duration and minimum-object-size
rules, then compute current vs optimized monthly cost.

Decision rule (evaluated in this order, first match wins):
  - age >= 180d AND rarely/never accessed          -> DEEP_ARCHIVE
  - age >= 90d  AND not accessed in last 30d        -> GLACIER_FR
  - age >= 60d  AND accessed <= 1x in last 30d       -> GLACIER_IR
  - age >= 30d  AND accessed <= 3x in last 30d       -> STANDARD_IA
  - otherwise                                        -> STANDARD

Objects smaller than a class's minimum billable size are kept on the
next-warmest eligible class, since AWS bills small objects in IA/Glacier
tiers as if they were the minimum size anyway (no savings, added risk).
"""
from .pricing import STORAGE_CLASSES


def _eligible(object_, class_key):
    rule = STORAGE_CLASSES[class_key]
    if object_["size_kb"] < rule["min_object_size_kb"]:
        return False
    if object_["age_days"] < rule["min_duration_days"]:
        return False
    return True


def recommend_class(object_):
    age = object_["age_days"]
    accesses = object_["access_count_30d"]
    last_access = object_["last_accessed_days_ago"]

    candidates = []
    if age >= 180 and accesses == 0 and last_access >= 90:
        candidates = ["DEEP_ARCHIVE", "GLACIER_FR", "GLACIER_IR", "STANDARD_IA"]
    elif age >= 90 and accesses <= 1:
        candidates = ["GLACIER_FR", "GLACIER_IR", "STANDARD_IA"]
    elif age >= 60 and accesses <= 1:
        candidates = ["GLACIER_IR", "STANDARD_IA"]
    elif age >= 30 and accesses <= 3:
        candidates = ["STANDARD_IA"]

    for c in candidates:
        if _eligible(object_, c):
            return c
    return "STANDARD"


def monthly_cost(size_kb, class_key):
    size_gb = size_kb / (1024 * 1024)
    return size_gb * STORAGE_CLASSES[class_key]["price_per_gb"]


def analyze_bucket(bucket_data):
    results = []
    total_current_cost = 0.0
    total_optimized_cost = 0.0
    total_size_kb = 0.0
    class_breakdown = {}

    for obj in bucket_data["objects"]:
        current_class = obj.get("storage_class", "STANDARD")
        recommended = recommend_class(obj)

        current_cost = monthly_cost(obj["size_kb"], current_class)
        optimized_cost = monthly_cost(obj["size_kb"], recommended)

        total_current_cost += current_cost
        total_optimized_cost += optimized_cost
        total_size_kb += obj["size_kb"]

        class_breakdown.setdefault(recommended, {"count": 0, "size_kb": 0.0, "cost": 0.0})
        class_breakdown[recommended]["count"] += 1
        class_breakdown[recommended]["size_kb"] += obj["size_kb"]
        class_breakdown[recommended]["cost"] += optimized_cost

        results.append({
            **obj,
            "current_class": current_class,
            "recommended_class": recommended,
            "current_monthly_cost": round(current_cost, 6),
            "optimized_monthly_cost": round(optimized_cost, 6),
            "monthly_savings": round(current_cost - optimized_cost, 6),
            "changed": current_class != recommended,
        })

    savings = total_current_cost - total_optimized_cost
    savings_pct = (savings / total_current_cost * 100) if total_current_cost > 0 else 0

    return {
        "bucket": bucket_data["bucket"],
        "region": bucket_data.get("region", "unknown"),
        "object_count": len(bucket_data["objects"]),
        "total_size_gb": round(total_size_kb / (1024 * 1024), 3),
        "total_current_monthly_cost": round(total_current_cost, 4),
        "total_optimized_monthly_cost": round(total_optimized_cost, 4),
        "monthly_savings": round(savings, 4),
        "annual_savings": round(savings * 12, 4),
        "savings_pct": round(savings_pct, 2),
        "objects_recommended_to_move": sum(1 for r in results if r["changed"]),
        "class_breakdown": {
            k: {"count": v["count"], "size_gb": round(v["size_kb"] / (1024 * 1024), 3), "monthly_cost": round(v["cost"], 4)}
            for k, v in class_breakdown.items()
        },
        "objects": results,
    }
