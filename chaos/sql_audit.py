"""Scénario 14 — requêtes SQL : N+1, scans complets, index manquants (lecture seule).

    docker compose -f chaos/docker-compose.lab.yml -p amm-lab exec -T backend python /chaos/sql_audit.py

Pour chaque endpoint de lecture : nombre de requêtes SQL à 50 puis 500 lignes par page (un
nombre qui grandit avec la page = N+1), temps SQL cumulé, et EXPLAIN (ANALYZE, BUFFERS) de la
requête la plus lente, dont on relève les parcours séquentiels (Seq Scan) sur les grosses tables.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from rest_framework_simplejwt.tokens import AccessToken  # noqa: E402

from apps.accounts.models import User  # noqa: E402
from apps.amm.models import MarketingAuthorization  # noqa: E402

ceo = User.objects.get(email="ceo@amm.local")
country_user = User.objects.filter(role=User.Role.COUNTRY_REGULATORY).order_by("email").first()
amm = MarketingAuthorization.objects.filter(renewals__isnull=False).first()


def client_for(user):
    return Client(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}", HTTP_HOST="localhost")


ENDPOINTS = [
    ("amms list", "/api/v1/amms?page_size={n}"),
    ("amms search", "/api/v1/amms?page_size={n}&search=PRODUIT"),
    ("amms filter urgency", "/api/v1/amms?page_size={n}&urgency=CRITIQUE"),
    ("amm detail", f"/api/v1/amms/{amm.pk}"),
    ("amm history", f"/api/v1/amms/{amm.pk}/history"),
    ("amm documents", f"/api/v1/amms/{amm.pk}/documents?group=period"),
    ("alerts open", "/api/v1/alerts?status=OPEN&page_size={n}"),
    ("renewals", "/api/v1/renewals?page_size={n}"),
    ("documents", "/api/v1/documents?page_size={n}"),
    ("analytics africa", "/api/v1/analytics/africa"),
    ("notifications", "/api/v1/notifications?page_size={n}"),
    ("products", "/api/v1/products?page_size={n}"),
]


def measure(client, path):
    with CaptureQueriesContext(connection) as ctx:
        started = time.monotonic()
        response = client.get(path)
        elapsed = time.monotonic() - started
    queries = ctx.captured_queries
    slowest = max(queries, key=lambda q: float(q["time"]), default=None)
    return {
        "status": response.status_code,
        "queries": len(queries),
        "sql_ms": round(sum(float(q["time"]) for q in queries) * 1000, 1),
        "total_ms": round(elapsed * 1000, 1),
        "slowest_sql": slowest["sql"] if slowest else None,
        "slowest_ms": round(float(slowest["time"]) * 1000, 1) if slowest else None,
    }


def explain(sql: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql)
        plan = "\n".join(row[0] for row in cursor.fetchall())
    seq = re.findall(r"Seq Scan on (\w+)", plan)
    total = re.search(r"Execution Time: ([\d.]+) ms", plan)
    return {"seq_scans": sorted(set(seq)), "execution_ms": float(total.group(1)) if total else None,
            "plan_head": plan.splitlines()[:12]}


report = {}
for user_label, user in (("ceo", ceo), ("pays", country_user)):
    client = client_for(user)
    for name, path in ENDPOINTS:
        small = measure(client, path.format(n=50))
        large = measure(client, path.format(n=500)) if "{n}" in path else None
        entry = {"page50": {k: v for k, v in small.items() if k != "slowest_sql"}}
        if large:
            entry["page500"] = {k: v for k, v in large.items() if k != "slowest_sql"}
            entry["n_plus_1_suspect"] = large["queries"] > small["queries"] + 2
        if small["slowest_sql"] and user_label == "ceo":
            try:
                entry["explain_slowest"] = explain(small["slowest_sql"])
            except Exception as exc:  # requête paramétrée non rejouable telle quelle
                entry["explain_slowest"] = {"error": str(exc)[:120]}
        report[f"{user_label} | {name}"] = entry

with connection.cursor() as cursor:
    cursor.execute(
        "select relname, seq_scan, idx_scan, n_live_tup from pg_stat_user_tables "
        "where n_live_tup > 500 order by seq_scan desc limit 12"
    )
    report["_table_scans"] = [
        {"table": r[0], "seq_scan": r[1], "idx_scan": r[2], "rows": r[3]} for r in cursor.fetchall()
    ]
print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
