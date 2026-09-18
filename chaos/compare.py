"""Tableau AVANT / APRÈS des scénarios rejoués à l'identique (chaos/results/*-{avant,apres}.json).

    python3 chaos/compare.py            # tableau Markdown sur stdout
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(name: str, label: str):
    path = RESULTS / f"{name}-{label}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fault_summary(r: dict) -> str:
    """Pour les scénarios à sonde : erreurs et latence pendant la panne, récupération."""
    during = r["phases"]["pendant"]
    kinds = r.get("per_kind", {})
    reads = [kinds[k]["pendant"] for k in ("list", "detail", "analytics", "alerts") if kinds.get(k, {}).get("pendant", {}).get("requests")]
    read_err = sum(w["errors"] for w in reads)
    read_req = sum(w["requests"] for w in reads)
    write = kinds.get("write", {}).get("pendant", {})
    login = r.get("actions", {}).get("login", {}).get("pendant", {})
    upload = r.get("actions", {}).get("upload", {})
    parts = [
        f"err {during.get('errors', 0)}/{during.get('requests', 0)}",
        f"lectures err {read_err}/{read_req}",
        f"écriture p95 {write.get('p95_ms', '–')} ms",
        f"p50 global {during.get('p50_ms', '–')} ms",
    ]
    if login:
        parts.append(f"connexion {login['attempts'] - login['failed']}/{login['attempts']} OK")
    if upload.get("persistence"):
        p = upload["persistence"]
        parts.append(f"uploads OK {p.get('saved_ok', 0)}, fantômes {p.get('saved_but_error', 0) + p.get('saved_after_timeout', 0)}")
    rec = r.get("recovered_s_after_heal")
    parts.append(f"récup. {rec} s" if rec is not None else "récup. –")
    integ = r.get("integrity", {})
    parts.append("intégrité OK" if integ.get("ok") else f"intégrité {integ.get('violations')}")
    return " ; ".join(parts)


def main():
    names = sorted({p.name.rsplit("-", 1)[0] for p in RESULTS.glob("*-avant.json")})
    out = ["| Scénario | Avant | Après |", "|---|---|---|"]
    for name in names:
        before, after = load(name, "avant"), load(name, "apres")
        if before is None:
            continue
        if "phases" in before:
            b = fault_summary(before)
            a = fault_summary(after) if after else "non rejoué"
        else:
            keep = lambda d: {k: v for k, v in d.items() if k not in ("scenario", "label", "resources_timeline", "diagnostic", "backend_log_tail", "attempts_per_second", "timeline")}
            b = json.dumps(keep(before), ensure_ascii=False)[:600]
            a = json.dumps(keep(after), ensure_ascii=False)[:600] if after else "non rejoué"
        out.append(f"| {name} | {b} | {a} |")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
