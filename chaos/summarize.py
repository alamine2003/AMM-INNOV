"""Chiffres clés de chaque scénario (avant / après), extraits des JSON de résultats.

    python3 chaos/summarize.py > chaos/results/summary.json

Le rapport ne cite que ces valeurs : aucune n'est recopiée à la main.
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(name: str, label: str):
    path = RESULTS / f"{name}-{label}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fault(r: dict) -> dict:
    kinds = r.get("per_kind", {})

    def during(kind):
        return kinds.get(kind, {}).get("pendant", {})

    reads = [during(k) for k in ("list", "detail", "analytics", "alerts") if during(k).get("requests")]
    out = {
        "requests": r["phases"]["pendant"].get("requests"),
        "errors": r["phases"]["pendant"].get("errors"),
        "p50_ms": r["phases"]["pendant"].get("p50_ms"),
        "p95_ms": r["phases"]["pendant"].get("p95_ms"),
        "max_ms": r["phases"]["pendant"].get("max_ms"),
        "read_errors": sum(w["errors"] for w in reads),
        "read_requests": sum(w["requests"] for w in reads),
        "read_p95_ms": max((w["p95_ms"] for w in reads), default=None),
        "write_p95_ms": during("write").get("p95_ms"),
        "write_max_ms": during("write").get("max_ms"),
        "users_affected": r["outage"].get("users_affected", 0),
        "outage_s": r["outage"].get("duration_s"),
        "recovered_s": r.get("recovered_s_after_heal"),
        "health_during": r["health"]["during"],
        "integrity_ok": r["integrity"].get("ok"),
        "violations": r["integrity"].get("violations"),
        "pg_conn_max": r.get("resources", {}).get("pg_connections_max"),
    }
    for name, action in r.get("actions", {}).items():
        p = action["pendant"]
        out[f"{name}_ok"] = f"{p['attempts'] - p['failed']}/{p['attempts']}"
        out[f"{name}_max_s"] = p["max_latency_s"]
        if action.get("persistence"):
            out[f"{name}_persistence"] = action["persistence"]
    return out


def main():
    names = sorted({p.name.rsplit("-", 1)[0] for p in RESULTS.glob("*-*.json")
                    if p.name.rsplit("-", 1)[1] in ("avant.json", "apres.json", "apres2.json")})
    summary = {}
    for name in names:
        entry = {}
        for label in ("avant", "apres", "apres2"):
            r = load(name, label)
            if r is None:
                continue
            if "phases" in r:
                entry[label] = fault(r)
            else:
                entry[label] = {k: v for k, v in r.items() if k not in (
                    "scenario", "label", "resources_timeline", "timeline", "attempts_per_second",
                    "backend_mem_samples")}
        summary[name] = entry
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
