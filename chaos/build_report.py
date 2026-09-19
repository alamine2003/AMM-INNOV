"""Page HTML du rapport de résilience, construite à partir des résultats mesurés.

    python3 chaos/build_report.py <sortie.html>
    python3 chaos/build_report.py --markdown docs/audit-resilience/RAPPORT.md

Chaque nombre affiché est lu dans chaos/results/*.json ; seuls les verdicts et les phrases
d'explication sont écrits à la main (dans ROWS et le texte ci-dessous).
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(name: str, label: str):
    path = RESULTS / f"{name}-{label}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fault(name: str, label: str) -> dict:
    r = load(name, label)
    if not r or "phases" not in r:
        return {}
    kinds = r.get("per_kind", {})

    def during(kind):
        return kinds.get(kind, {}).get("pendant", {})

    reads = [during(k) for k in ("list", "detail", "analytics", "alerts") if during(k).get("requests")]
    out = {
        "err": r["phases"]["pendant"].get("errors", 0),
        "req": r["phases"]["pendant"].get("requests", 0),
        "p50": r["phases"]["pendant"].get("p50_ms"),
        "read_err": sum(w["errors"] for w in reads),
        "read_req": sum(w["requests"] for w in reads),
        "read_p95": max((w["p95_ms"] for w in reads), default=None),
        "write_p95": during("write").get("p95_ms"),
        "users": r["outage"].get("users_affected", 0),
        "recovered": r.get("recovered_s_after_heal"),
        "integrity": r["integrity"].get("ok"),
        "violations": r["integrity"].get("violations") or {},
    }
    for action_name, action in r.get("actions", {}).items():
        p = action["pendant"]
        out[action_name] = (p["attempts"] - p["failed"], p["attempts"], p["max_latency_s"])
        if action.get("persistence"):
            pers = action["persistence"]
            out[f"{action_name}_ghost"] = pers.get("saved_but_error", 0) + pers.get("saved_after_timeout", 0)
    return out


def ms(value) -> str:
    if value is None:
        return "–"
    return f"{value / 1000:.1f} s" if value >= 1000 else f"{value} ms"


def ratio(t) -> str:
    return f"{t[0]}/{t[1]}" if t else "–"


def esc(text) -> str:
    return html.escape(str(text))


# --------------------------------------------------------------------------- matrice

def m_fault(name, focus):
    """Résumé chiffré d'un scénario à sonde, avant puis après."""
    def one(label):
        f = fault(name, label)
        if not f:
            return "non rejoué"
        parts = []
        for key in focus:
            if key == "reads":
                parts.append(f"lectures {f['read_err']}/{f['read_req']} en échec, p95 {ms(f['read_p95'])}")
            elif key == "writes":
                parts.append(f"écritures p95 {ms(f['write_p95'])}")
            elif key == "login" and f.get("login"):
                parts.append(f"connexions {ratio(f['login'])}")
            elif key == "upload" and f.get("upload"):
                ghost = f.get("upload_ghost")
                parts.append(f"uploads {ratio(f['upload'])} (max {f['upload'][2]:.1f} s)"
                             + (f", {ghost} fantôme(s)" if ghost else ""))
            elif key == "renewal" and f.get("renewal"):
                parts.append(f"décisions {ratio(f['renewal'])}")
            elif key == "errors":
                parts.append(f"{f['err']}/{f['req']} requêtes en échec")
            elif key == "users":
                parts.append(f"{f['users']} utilisateur(s) touché(s)")
            elif key == "recovery":
                parts.append(f"reprise {f['recovered']} s" if f["recovered"] is not None else "pas de reprise")
            elif key == "p50":
                parts.append(f"médiane {ms(f['p50'])}")
        if not f["integrity"]:
            parts.append("intégrité : " + ", ".join(f"{k} ×{v}" for k, v in f["violations"].items()))
        return " · ".join(parts)
    return one("avant"), one("apres")


def m_custom(name, fn):
    before, after = load(name, "avant"), load(name, "apres")
    return (fn(before) if before else "non joué"), (fn(after) if after else "non rejoué")


PLACEHOLDER = object()


def load_curve(label: str):
    r = load("s05_load_steps", label)
    if not r:
        return []
    return [(int(v), s["rps"], s["latency_ms"].get("p(95)"), s["latency_ms"].get("med"), s["error_rate"])
            for v, s in sorted(r["steps"].items(), key=lambda kv: int(kv[0]))]


def svg_load_chart(series: list[tuple[str, str, list]]) -> str:
    """Débit (req/s) selon le nombre d'utilisateurs, échelle log en x ; une courbe par code."""
    import math

    width, height, left, right, top, bottom = 680, 300, 56, 24, 20, 48
    xs = [10, 30, 100, 250, 500, 1000]
    max_rps = max([p[1] for _, _, pts in series for p in pts] + [1])
    y_max = math.ceil(max_rps / 50) * 50

    def x(v):
        return left + (math.log10(v) - 1) / 2 * (width - left - right)

    def y(v):
        return top + (1 - v / y_max) * (height - top - bottom)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Débit selon le nombre d\'utilisateurs" class="chart">']
    for tick in range(0, y_max + 1, 50):
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" class="grid"/>')
        out.append(f'<text x="{left - 8}" y="{y(tick) + 4:.1f}" class="axis" text-anchor="end">{tick}</text>')
    for v in xs:
        out.append(f'<text x="{x(v):.1f}" y="{height - bottom + 18}" class="axis" text-anchor="middle">{v}</text>')
    out.append(f'<text x="{(left + width - right) / 2:.0f}" y="{height - 8}" class="axis-title" text-anchor="middle">utilisateurs simultanés (échelle log)</text>')
    out.append(f'<text x="14" y="{top + 4}" class="axis-title">req/s</text>')
    for label, css, pts in series:
        if not pts:
            continue
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(p[0]):.1f},{y(p[1]):.1f}" for i, p in enumerate(pts))
        out.append(f'<path d="{path}" class="line {css}"/>')
        for p in pts:
            out.append(f'<circle cx="{x(p[0]):.1f}" cy="{y(p[1]):.1f}" r="3.5" class="dot {css}"><title>{label} — {p[0]} utilisateurs : {p[1]} req/s, p95 {ms(p[2])}</title></circle>')
        last = pts[-1]
        out.append(f'<text x="{x(last[0]) - 6:.1f}" y="{y(last[1]) - 9:.1f}" class="label {css}" text-anchor="end">{esc(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_bars(rows: list[tuple[str, float, float]], unit: str, title: str) -> str:
    """Barres horizontales avant/après (échelle log10 quand l'écart dépasse 100×)."""
    import math

    width, row_h, left, right = 680, 46, 210, 70
    height = row_h * len(rows) + 30
    vmax = max([max(a, b) for _, a, b in rows] + [1])
    use_log = vmax / max(min([v for _, a, b in rows for v in (a, b) if v > 0] + [1]), 1) > 100

    def w(v):
        if v <= 0:
            return 0
        if use_log:
            return (math.log10(max(v, 1)) / math.log10(vmax)) * (width - left - right)
        return v / vmax * (width - left - right)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}" class="chart">']
    for i, (label, before, after) in enumerate(rows):
        y0 = 10 + i * row_h
        out.append(f'<text x="{left - 10}" y="{y0 + 18}" class="axis" text-anchor="end">{esc(label)}</text>')
        for j, (value, css, tag) in enumerate(((before, "before", "avant"), (after, "after", "après"))):
            yy = y0 + j * 16
            out.append(f'<rect x="{left}" y="{yy}" width="{max(w(value), 2):.1f}" height="12" class="bar {css}"><title>{tag} : {value:g} {unit}</title></rect>')
            out.append(f'<text x="{left + max(w(value), 2) + 6:.1f}" y="{yy + 10}" class="value">{value:g} {unit}</text>')
    out.append(f'<text x="{left}" y="{height - 4}" class="axis-title">{"échelle logarithmique · " if use_log else ""}{esc(title)}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- verdicts

def statuses(d) -> str:
    """{'200': 15, '502': 5} → « 15 × 200, 5 × 502 »."""
    return ", ".join(f"{n} × {code}" for code, n in sorted(d.items()))


def c_sigterm(r):
    return (f"requêtes en vol : {statuses(r['inflight_statuses'])} · "
            + (f"de retour en {r['back_after_s']} s" if r.get("back_after_s") else "processus vivant mais sourd, jamais redémarré"))


def c_nginx(r):
    return ("API joignable (200) avec Grafana arrêté" if r["api_status_with_grafana_down"] == 200
            else f"API injoignable (statut {r['api_status_with_grafana_down']}) : nginx refuse de démarrer")


def c_worker_kill(r):
    e = r["emails"]
    return (f"e-mails {e['marked_sent']}/{e['created']} envoyés · dossier après relance : {r['dossier_after_relaunch']}"
            f" (relance {r['dossier_relaunch']['status']})")


def c_worker_term(r):
    e = r["emails"]
    return f"arrêt en {r['stop_took_s']} s · e-mails {e['marked_sent']}/{e['created']} envoyés, {r['gmail_messages_received']} reçus par Gmail"


def c_restart(r):
    late = r["late_database"]
    back = late.get("api_back_after_db_start_s")
    return (f"démarrage à froid {r['cold_start']['api_ready_s']} s · base tardive : "
            + (f"API de retour {back} s après la base" if back is not None else
               f"backend sain en direct ({late.get('backend_direct_back_s')} s) mais injoignable via nginx (IP {late.get('backend_ip_before')} → {late.get('backend_ip_after')})"))


def c_downloads(r):
    side = r["unrelated_list_during"]
    unrelated = statuses({str(c): sum(1 for x, _ in side if x == c) for c, _ in side})
    return (f"téléchargements : {statuses(r['download_statuses'])} (max {r['download_latency_max_s']} s)"
            f" · listes d'AMM sans rapport pendant ce temps : {unrelated}")


def c_pool(r):
    kind = "HTML" if any("<!doctype" in b.lower() for b in r.get("error_bodies", [])) else "JSON"
    return f"{r['concurrent']} requêtes : {statuses(r['statuses'])} ({kind}) · médiane {r['p50_s']} s"


def c_gmail(r):
    modes = r["modes"]
    final = modes.get("after_sweep")
    if final:
        dup = modes["ack_lost"]
        return (f"e-mails finalement envoyés : {final['emails_sent']}/{final['emails_total']} "
                f"(panne de 3 min : {final['outage_3min_sent']}/5) · accusé perdu : "
                f"{dup['gmail_messages_received']} envois pour {dup['emails']['created']} e-mails"
                f" · aperçus retardés {modes['slow']['preview_latency_s']} s")
    lost = [m for m in ("http500", "http429", "invalid", "down") if modes[m]["emails"]["marked_sent"] == 0]
    long = modes["outage_3min"]["emails"]
    dup = modes["ack_lost"]
    return (f"perdus après 60 s de panne : {', '.join(lost) or 'aucun mode'} · panne de 3 min : {long['marked_sent']}/{long['created']} envoyés"
            f" · accusé perdu : {dup['gmail_messages_received']} envois pour {dup['emails']['created']} e-mails"
            f" · aperçus retardés {modes['slow']['preview_latency_s']} s")


def c_concurrency(r):
    return (f"même décision ×10 → {r['a_same_decision_x10']['renewals_created']} renouvellement(s) · "
            f"mise à jour perdue : {'oui' if r['c_lost_update']['lost'] else 'non'} ({r['c_lost_update']['history_regressions']} régressions) · "
            f"remplacements ×8 → {r['e_replace_x8']['current_successors']} version(s) courante(s)")


def c_disk(r):
    lv = r["levels"]
    pg = lv["postgres_100"]["window"]
    return (f"base à 80/90/95 % : aucune alerte · base à 100 % : {pg.get('errors')}/{pg.get('requests')} en échec, santé {lv['postgres_100']['health']['status']} · "
            + ("intégrité OK" if r["integrity"]["ok"] else "intégrité : " + ", ".join(f"{k} ×{v}" for k, v in r["integrity"]["violations"].items())))


def c_memory(r):
    peak = max((float(m.rstrip("MiB")) for m in r.get("backend_mem_samples") or [] if m.endswith("MiB")), default=None)
    return (f"8 archives : {statuses(r['archive_statuses'])} · redémarrages du web {r['backend_restarts_during']} · "
            f"autres utilisateurs : {r['collateral']['window']['errors']} erreur(s)"
            + (f" · mémoire web jusqu'à {peak:.0f} Mio (relevé toutes les 3 s)" if peak else ""))


def c_herd(r):
    return f"pic {r['peak_attempts_per_second_after_kill']} reconnexions/s ({r['attempts_after_kill']} au total)"


def c_ampli(r):
    return f"{r['events_delivered']} événements pour 20 écritures ({r['events_per_write_per_client']} par client et par écriture)"


def c_spike(r):
    k = r["k6"]
    return f"{k['rps']} req/s · médiane {ms(k['latency_ms']['med'])} · p99 {ms(k['latency_ms']['p(99)'])} · erreurs {k['error_rate']}"


def c_load(r):
    steps = r["steps"]
    best = max(steps.items(), key=lambda kv: kv[1]["rps"])
    last = steps["1000"]
    return (f"plafond {best[1]['rps']} req/s à {best[0]} utilisateurs · 1 000 utilisateurs : médiane {ms(last['latency_ms']['med'])}, "
            f"erreurs {last['error_rate']}")


def c_worker_down(r):
    e = r["emails"]
    return f"{r['queued_while_down']} tâches en file · vidée en {r['drained_after_restart_s']} s · e-mails {e['marked_sent']}/{e['created']}, reçus {r['gmail_messages_received']}"


def c_queue(r):
    return f"file : {r['queued_before_kill']} avant SIGKILL, {r['queued_after_restart']} après (Redis AOF)"


def c_p3b(r):
    e = r["emails"]
    return (f"API : {r['api']['window']['errors']} erreur(s) · e-mails {e['marked_sent']}/{e['created']} après retour de Gmail"
            f" · reçus {r['gmail_messages_received']}")


F, P, S = "FAILURE", "PARTIAL", "SUCCESS"

# (groupe, id, panne injectée, verdict avant, verdict après, résumé chiffré (avant, après))
ROWS = [
    ("Redis", "s03a", "Redis tué 60 s", F, S, lambda: m_fault("s03a_redis_kill", ["login", "writes", "upload"])),
    ("Redis", "s03b", "Redis figé 60 s", F, S, lambda: m_fault("s03b_redis_hang", ["login", "writes", "upload"])),
    ("Redis", "s03c", "Redis figé 60 s sous 40 utilisateurs", F, S, lambda: m_fault("s03c_redis_hang_load", ["reads", "writes", "users"])),
    ("Redis", "s04", "Latence Redis 1 s", P, S, lambda: m_fault("s04_redis_latency_1000", ["writes", "login"])),
    ("Redis", "s04", "Latence Redis 3 s", F, S, lambda: m_fault("s04_redis_latency_3000", ["writes", "login"])),
    ("PostgreSQL", "s02a", "PostgreSQL tué 30 s", P, P, lambda: m_fault("s02a_pg_kill", ["errors", "reads", "recovery"])),
    ("PostgreSQL", "s02f", "Redémarrage rapide de PostgreSQL", S, S, lambda: m_fault("s02f_pg_quick_restart", ["errors", "recovery"])),
    ("PostgreSQL", "s02b", "PostgreSQL figé 60 s", P, P, lambda: m_fault("s02b_pg_hang", ["reads", "renewal", "recovery"])),
    ("PostgreSQL", "s02c", "Latence PostgreSQL 1 s", P, P, lambda: m_fault("s02c_pg_latency_1000", ["reads", "writes"])),
    ("PostgreSQL", "s02d", "Coupures TCP en pleine transaction", P, S, lambda: m_fault("s02d_pg_reset_mid_tx", ["errors", "recovery"])),
    ("PostgreSQL", "s02e", "Pool saturé (300 requêtes lentes, pool chaud)", F, P, lambda: m_custom("s02e_pg_pool_saturation", c_pool)),
    ("Processus", "s01", "Web tué (SIGKILL) ×4", P, P, lambda: m_fault("s01_backend_crash", ["errors", "users", "recovery"])),
    ("Processus", "s11a", "Web arrêté (SIGTERM) en charge", F, S, lambda: m_custom("s11a_backend_sigterm", c_sigterm)),
    ("Processus", "s11b", "Web tué (SIGKILL) en charge", P, P, lambda: m_custom("s11b_backend_sigkill", c_sigterm)),
    ("Processus", "s11c", "nginx redémarré, Grafana absent", F, S, lambda: m_custom("s11c_nginx_restart_without_grafana", c_nginx)),
    ("Processus", "s16", "Redémarrage complet, base tardive", F, S, lambda: m_custom("s16_full_restart", c_restart)),
    ("Stockage", "s10a", "MinIO arrêté 60 s", P, S, lambda: m_fault("s10a_storage_down", ["reads", "upload"])),
    ("Stockage", "s10b", "MinIO figé 60 s", P, P, lambda: m_fault("s10b_storage_hang", ["reads", "upload"])),
    ("Stockage", "s10c", "20 téléchargements, MinIO arrêté", F, S, lambda: m_custom("s10c_storage_downloads", c_downloads)),
    ("Tâches", "s12a", "Worker arrêté 60 s", S, S, lambda: m_custom("s12a_worker_down", c_worker_down)),
    ("Tâches", "s12b", "Worker tué en pleine tâche", F, S, lambda: m_custom("s12b_worker_kill_mid_task", c_worker_kill)),
    ("Tâches", "s11d", "Worker arrêté pendant des envois lents", F, S, lambda: m_custom("s11d_worker_sigterm_long_task", c_worker_term)),
    ("Tâches", "s11e", "Redis tué avec 200 tâches en file", S, S, lambda: m_custom("s11e_redis_kill_with_queue", c_queue)),
    ("Externe", "s13", "API Gmail : 500, 429, invalide, lente, figée, coupée", F, P, lambda: m_custom("s13_gmail_failures", c_gmail)),
    ("Données", "s15", "Écritures concurrentes sur une même ressource", F, S, lambda: m_custom("s15_concurrency", c_concurrency)),
    ("Données", "s09", "Disque plein (80 → 100 %)", F, P, lambda: m_custom("s09_disk_full", c_disk)),
    ("Charge", "s05", "Paliers 10 → 1 000 utilisateurs", P, P, lambda: m_custom("s05_load_steps", c_load)),
    ("Charge", "s06", "Pic 10 → 1 000 en 5 s", P, P, lambda: m_custom("s06_spike", c_spike)),
    ("Ressources", "s07", "CPU bridé à 0,15 cœur (web)", S, S, lambda: m_fault("s07_cpu_backend", ["errors", "p50"])),
    ("Ressources", "s08", "8 archives ZIP de scans lourds", F, S, lambda: m_custom("s08_memory", c_memory)),
    ("Réseau", "s04b", "Réseau instable (jitter, paquets, pertes)", P, P, lambda: m_fault("s04b_network_unstable", ["errors", "reads", "login"])),
    ("Réseau", "s04c", "Partition réseau 30 s", P, P, lambda: m_fault("s04c_network_partition", ["errors", "recovery"])),
    ("Temps réel", "s17", "Web tué, 300 clients WebSocket", P, P, lambda: m_custom("s17_ws_reconnect_herd", c_herd)),
    ("Temps réel", "s18", "20 écritures, 100 clients connectés", P, S, lambda: m_custom("s18_event_amplification", c_ampli)),
    ("Combinées", "p3a", "40 utilisateurs + Redis tué + PostgreSQL lent", F, P, lambda: m_fault("p3a_load_redis_down_pg_slow", ["login", "writes", "upload"])),
    ("Combinées", "p3b", "Web tué + worker arrêté + Gmail en panne", F, P, lambda: m_custom("p3b_crash_worker_down_gmail_down", c_p3b)),
    ("Combinées", "p3c", "CPU web bridé + PostgreSQL lent + pic à 500", P, P, lambda: m_custom("p3c_cpu_dblatency_spike", c_spike)),
]


CSS = """
:root{
  --paper:#F6F5F9; --surface:#FFFFFF; --ink:#1C1A26; --muted:#5E5A6E; --rule:#DFDBE8;
  --stamp:#4B3BA8; --stamp-soft:#ECE8FA;
  --fail:#B42318; --fail-soft:#FDEBE9; --partial:#9A5B06; --partial-soft:#FDF1DD;
  --pass:#23693F; --pass-soft:#E4F3EA; --na:#6B6878; --na-soft:#EFEDF3;
  --before:#B7B1C9; --after:#4B3BA8;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --cond:"IBM Plex Sans Condensed","IBM Plex Sans",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#14131A; --surface:#1C1B24; --ink:#ECEAF3; --muted:#A5A1B6; --rule:#322F3F;
    --stamp:#B1A5FF; --stamp-soft:#28233F;
    --fail:#FF8A80; --fail-soft:#3A1C1A; --partial:#F4B35A; --partial-soft:#382813;
    --pass:#79D39F; --pass-soft:#15301F; --na:#A5A1B6; --na-soft:#262431;
    --before:#5A5470; --after:#B1A5FF;
  }
}
:root[data-theme="dark"]{
  --paper:#14131A; --surface:#1C1B24; --ink:#ECEAF3; --muted:#A5A1B6; --rule:#322F3F;
  --stamp:#B1A5FF; --stamp-soft:#28233F;
  --fail:#FF8A80; --fail-soft:#3A1C1A; --partial:#F4B35A; --partial-soft:#382813;
  --pass:#79D39F; --pass-soft:#15301F; --na:#A5A1B6; --na-soft:#262431;
  --before:#5A5470; --after:#B1A5FF;
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans);padding-inline:16px;padding-block:28px 64px}
.page{max-width:1080px;margin:0 auto;display:grid;gap:44px}
a{color:var(--stamp)} a:focus-visible,summary:focus-visible{outline:2px solid var(--stamp);outline-offset:2px}
h1,h2,h3{font-family:var(--cond);text-wrap:balance;line-height:1.15;margin:0}
h1{font-size:clamp(30px,5vw,46px);font-weight:700;letter-spacing:-.01em}
h2{font-size:26px;font-weight:600}
h3{font-size:17px;font-weight:600}
p{margin:0;max-width:70ch}
.prose{display:grid;gap:12px}
.eyebrow{font:600 12px/1.2 var(--cond);letter-spacing:.14em;text-transform:uppercase;color:var(--stamp)}
.lede{font-size:18px;color:var(--ink);max-width:62ch}
.muted{color:var(--muted)}
header.hero{display:grid;gap:16px;border-bottom:1px solid var(--rule);padding-bottom:28px}
.dossier{display:flex;flex-wrap:wrap;gap:8px 28px;font-size:13px;color:var(--muted)}
.dossier b{font:500 13px var(--mono);color:var(--ink)}
section{display:grid;gap:18px}
.section-head{display:grid;gap:6px}
.stamp{display:inline-block;font:600 11px/1 var(--cond);letter-spacing:.1em;text-transform:uppercase;
  padding:5px 7px 4px;border:1.5px solid currentColor;border-radius:3px;white-space:nowrap}
.stamp.FAILURE{color:var(--fail);background:var(--fail-soft)}
.stamp.PARTIAL{color:var(--partial);background:var(--partial-soft)}
.stamp.SUCCESS{color:var(--pass);background:var(--pass-soft)}
.stamp.NA{color:var(--na);background:var(--na-soft)}
.score{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.score .card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:16px 18px;display:grid;gap:10px}
.score .card .row{display:flex;justify-content:space-between;align-items:center;gap:10px;font-variant-numeric:tabular-nums}
.score .big{font:600 28px/1 var(--mono)}
.verdict-seal{transform:rotate(-2deg);display:inline-block}
.table-wrap{overflow-x:auto;border:1px solid var(--rule);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid var(--rule)}
thead th{font:600 12px var(--cond);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);background:var(--paper);position:sticky;top:0}
tbody tr:last-child td{border-bottom:0}
td.id{font:500 12.5px var(--mono);color:var(--stamp);white-space:nowrap}
tr.grp td{font:600 12px var(--cond);letter-spacing:.1em;text-transform:uppercase;color:var(--stamp);background:var(--stamp-soft);padding:7px 12px}
td.metric{font-size:12.5px;color:var(--muted);min-width:230px}
td.metric b{color:var(--ink);font-weight:500}
.matrix td.inj{min-width:190px;font-weight:500}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
figure{margin:0;background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:16px;display:grid;gap:8px}
figcaption{font-size:13px;color:var(--muted)}
.chart{width:100%;height:auto;display:block}
.chart .grid{stroke:var(--rule);stroke-width:1}
.chart .axis{fill:var(--muted);font:11px var(--mono)}
.chart .axis-title{fill:var(--muted);font:11px var(--sans)}
.chart .value{fill:var(--ink);font:11px var(--mono)}
.chart .line{fill:none;stroke-width:2.2}
.chart .line.before,.chart .dot.before{stroke:var(--before)} .chart .dot.before{fill:var(--before)}
.chart .line.after,.chart .dot.after{stroke:var(--after)} .chart .dot.after{fill:var(--after)}
.chart .line.after2,.chart .dot.after2{stroke:var(--pass)} .chart .dot.after2{fill:var(--pass)}
.chart .label{font:600 11px var(--cond);letter-spacing:.04em}
.chart .label.before{fill:var(--muted)} .chart .label.after{fill:var(--after)} .chart .label.after2{fill:var(--pass)}
.chart .bar.before{fill:var(--before)} .chart .bar.after{fill:var(--after)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.incidents{display:grid;gap:10px}
.incident{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;display:grid;gap:6px}
.incident .top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.incident .code{font:500 12.5px var(--mono);color:var(--stamp)}
.incident p{font-size:14px}
.incident .lbl{font:600 11px var(--cond);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-right:6px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.cols .col{display:grid;gap:8px;align-content:start}
.cols ul{margin:0;padding-left:18px;display:grid;gap:6px;font-size:14px}
pre.mermaid{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:12px;overflow-x:auto;margin:0}
ul.limits{margin:0;padding-left:18px;display:grid;gap:8px;max-width:78ch}
code{font:13px var(--mono);background:var(--stamp-soft);padding:1px 5px;border-radius:3px}
footer{border-top:1px solid var(--rule);padding-top:18px;font-size:13px;color:var(--muted)}
@media (max-width:560px){ body{font-size:14.5px} .lede{font-size:16.5px} th,td{padding:9px 10px} }
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


def stamp(verdict) -> str:
    if verdict is None:
        return '<span class="stamp NA">non mesuré</span>'
    return f'<span class="stamp {verdict}">{verdict}</span>'


def render(content: dict) -> str:
    rows_html, counts, current = [], {"avant": {}, "apres": {}}, None
    for group, sid, injection, before, after, metric in ROWS:
        b_txt, a_txt = metric()
        if group != current:
            current = group
            rows_html.append(f"<tr class='grp'><td colspan='6'>{esc(group)}</td></tr>")
        for label, v in (("avant", before), ("apres", after)):
            if v:
                counts[label][v] = counts[label].get(v, 0) + 1
        rows_html.append(
            f"<tr><td class='id'>{esc(sid)}</td><td class='inj'>{esc(injection)}</td>"
            f"<td>{stamp(before)}</td><td class='metric'>{esc(b_txt)}</td>"
            f"<td>{stamp(after)}</td><td class='metric'>{esc(a_txt)}</td></tr>")

    def score(label):
        c = counts[label]
        return "".join(f"<div class='row'><span class='stamp {v}'>{v}</span><span class='big'>{c.get(v, 0)}</span></div>"
                       for v in ("FAILURE", "PARTIAL", "SUCCESS"))

    return f"""<title>Audit de résilience AMM INNOV</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap">
<style>{CSS}</style>
<main class="page">
{content['hero']}
<section id="bilan"><div class="section-head"><p class="eyebrow">Bilan des crash tests</p><h2>{len(ROWS)} pannes injectées, avant et après correction</h2></div>
<div class="score"><div class="card"><p class="eyebrow">Code d'origine</p>{score('avant')}</div>
<div class="card"><p class="eyebrow">Code corrigé</p>{score('apres')}</div>
<div class="card"><p class="eyebrow">Intégrité des données</p><p>{content['integrity_card']}</p></div></div></section>
<section id="matrice"><div class="section-head"><p class="eyebrow">Matrice</p><h2>Crash tests réalisés</h2>
<p class="muted">Même script, mêmes données, même injection avant et après : seul le code change. Chiffres mesurés pendant la panne ; « fantôme » = enregistré mais annoncé en échec.</p></div>
<div class="table-wrap"><table class="matrix"><thead><tr><th>Test</th><th>Panne injectée</th><th>Avant</th><th>Mesure avant</th><th>Après</th><th>Mesure après</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody></table></div></section>
{content['sections']}
<footer>{content['footer']}</footer>
</main>"""


def capacity_table() -> str:
    labels = (("avant", "avant, 1 processus"), ("apres", "après, 1 processus"), ("apres2", "après, 2 processus"))
    curves = {k: dict((p[0], p) for p in load_curve(k)) for k, _ in labels}
    head = "".join(f"<th>{esc(t)}</th>" for _, t in labels if curves[_])
    rows = []
    for vus in (10, 30, 100, 250, 500, 1000):
        cells = []
        for key, _ in labels:
            if not curves[key]:
                continue
            p = curves[key].get(vus)
            cells.append(f"<td class='metric'><b>{p[1]} req/s</b> · p50 {ms(p[3])} · p95 {ms(p[2])} · erreurs {p[4]}</td>" if p else "<td>–</td>")
        rows.append(f"<tr><td class='id'>{vus}</td>{''.join(cells)}</tr>")
    return (f"<div class='table-wrap'><table><thead><tr><th>Utilisateurs</th>{head}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def recovery_table() -> str:
    def rec(name, label):
        f = fault(name, label)
        return f"{f['recovered']} s" if f and f.get("recovered") is not None else "–"

    def sig(label):
        r = load("s11a_backend_sigterm", label)
        return (f"{r['back_after_s']} s" if r and r.get("back_after_s") else "aucune reprise (manuel)") if r else "–"

    def restart(label):
        r = load("s16_full_restart", label)
        if not r:
            return "–"
        back = r["late_database"].get("api_back_after_db_start_s")
        return f"{back} s" if back is not None else "aucune reprise via nginx (manuel)"

    def worker(label):
        r = load("s12b_worker_kill_mid_task", label)
        if not r:
            return "–", "–"
        e = r["emails"]
        lost = e["created"] - e["marked_sent"]
        mttr = ("rattrapage ≤ 15-30 min" if e["marked_sent"] == e["created"] else "aucune reprise")
        return mttr, (f"{lost} e-mail(s) non envoyé(s)" if lost else "0")

    def gmail(label):
        r = load("s13_gmail_failures", label)
        if not r:
            return "–"
        e = r["modes"]["outage_3min"]["emails"]
        final = r["modes"].get("after_sweep")
        sent = final["outage_3min_sent"] if final else e["marked_sent"]
        return f"{e['created'] - sent} e-mail(s) sur {e['created']} perdus" if sent < e["created"] else "0"

    def disk(label):
        r = load("s09_disk_full", label)
        if not r:
            return "–"
        v = (r.get("integrity") or {}).get("violations") or {}
        return f"{v['history_matches_rows']} AMM sans historique" if v.get("history_matches_rows") else "0"

    w_before, w_before_rpo = worker("avant")
    w_after, w_after_rpo = worker("apres")
    rows = [
        ("Web tué (SIGKILL)", "502 immédiat", rec("s01_backend_crash", "avant"), rec("s01_backend_crash", "apres"), "0", "0"),
        ("Web arrêté (SIGTERM)", "aucune", sig("avant"), sig("apres"), "0", "0"),
        ("PostgreSQL tué 30 s", "/health", rec("s02a_pg_kill", "avant"), rec("s02a_pg_kill", "apres"), "0", "0"),
        ("PostgreSQL figé 60 s", "/health (503 après)", rec("s02b_pg_hang", "avant"), rec("s02b_pg_hang", "apres"), "0 (1 décision fantôme)", "0"),
        ("Redis tué 60 s", "compteurs de dégradation (après)", rec("s03a_redis_kill", "avant"), rec("s03a_redis_kill", "apres"), "0", "0"),
        ("Stockage arrêté 60 s", "503 explicite (après)", rec("s10a_storage_down", "avant"), rec("s10a_storage_down", "apres"), "0", "0"),
        ("Worker tué en pleine tâche", "v_ops_backlog (après)", w_before, w_after, w_before_rpo, w_after_rpo),
        ("Gmail indisponible 3 min", "last_error, v_ops_backlog (après)", "aucune reprise", "relances, puis rattrapage /5 min", gmail("avant"), gmail("apres")),
        ("Base absente au démarrage (serveur unique)", "aucune", restart("avant"), restart("apres"), "0", "0"),
        ("Disque de la base plein", "aucune avant 100 %", "au nettoyage", "au nettoyage", disk("avant"), disk("apres")),
    ]
    body = "".join(f"<tr><td class='inj'>{esc(a)}</td><td class='metric'>{esc(b)}</td><td class='metric'>{esc(c)}</td>"
                   f"<td class='metric'>{esc(d)}</td><td class='metric'>{esc(e)}</td><td class='metric'>{esc(f)}</td></tr>"
                   for a, b, c, d, e, f in rows)
    return ("<div class='table-wrap'><table><thead><tr><th>Panne</th><th>Détection</th><th>Reprise avant</th>"
            "<th>Reprise après</th><th>Perte avant</th><th>Perte après</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def observability_block() -> str:
    r = load("s19_observability", "apres")
    if not r:
        return "<p class='muted'>Démonstration non jouée.</p>"
    events = "".join(
        f"<tr><td class='id'>{esc(e['ts'][11:19])}</td><td><span class='stamp {'FAILURE' if e['level'] == 'ERROR' else 'SUCCESS'}'>{esc(e['level'])}</span></td>"
        f"<td class='metric'><b>{esc(e['msg'])}</b><br>request_id {esc(e['request_id'])}</td></tr>"
        for e in r["breaker_events"])
    line = r.get("sample_access_line") or {}
    counters = " · ".join(esc(c) for c in r["degraded_counters"]) or "–"
    return (f"<div class='table-wrap'><table><thead><tr><th>Heure</th><th>Niveau</th><th>Message</th></tr></thead><tbody>{events}</tbody></table></div>"
            f"<p class='muted'>Compteur : <code>{counters}</code> · {r['json_log_lines']} lignes d'accès JSON, "
            f"<b>{r['requests_5xx_in_logs']}</b> réponse(s) 5xx, <b>{r['users_with_5xx']}</b> utilisateur(s) touché(s). "
            f"Exemple : <code>{esc(json.dumps({k: line.get(k) for k in ('path', 'status', 'duration_ms', 'user_id', 'request_id')}, ensure_ascii=False))}</code></p>")


def integrity_card() -> str:
    counts = {}
    for label in ("avant", "apres"):
        bad = total = 0
        for path in RESULTS.glob(f"*-{label}.json"):
            try:
                data = json.loads(path.read_text())
            except ValueError:
                continue
            integ = data.get("integrity")
            if not isinstance(integ, dict) or integ.get("ok") is None:
                continue
            total += 1
            bad += 0 if integ["ok"] else 1
        counts[label] = (bad, total)
    b, a = counts["avant"], counts["apres"]
    return (f"<b>{b[0]}</b> scénario(s) sur {b[1]} laissaient des données incohérentes avant, "
            f"<b>{a[0]}</b> sur {a[1]} après (contrôle automatique des 12 invariants après chaque test).")


def main():
    import report_text

    content = {"hero": report_text.HERO, "sections": report_text.SECTIONS, "footer": report_text.FOOTER,
               "integrity_card": integrity_card()}
    content["sections"] = (content["sections"].replace("{{CAPACITY_TABLE}}", capacity_table())
                           .replace("{{RECOVERY_TABLE}}", recovery_table())
                           .replace("{{OBSERVABILITY}}", observability_block()))
    content["sections"] = content["sections"].replace("{{LOAD_CHART}}", svg_load_chart([
        ("avant", "before", load_curve("avant")),
        ("après", "after", load_curve("apres")),
        ("après, 2 processus", "after2", load_curve("apres2")),
    ]))
    bars = []
    for label, name, key in (
        ("Redis figé ×40 · lectures", "s03c_redis_hang_load", "read_p95"),
        ("Redis figé ×40 · écritures", "s03c_redis_hang_load", "write_p95"),
        ("Redis tué · écritures", "s03a_redis_kill", "write_p95"),
        ("Redis +3 s · écritures", "s04_redis_latency_3000", "write_p95"),
        ("Pannes combinées · écritures", "p3a_load_redis_down_pg_slow", "write_p95"),
    ):
        before, after = fault(name, "avant"), fault(name, "apres")
        if before and after:
            bars.append((label, before[key] or 0, after[key] or 0))
    content["sections"] = content["sections"].replace(
        "{{BARS}}", svg_bars(bars, "ms", "latence p95 pendant la panne (ms)") if bars else "")
    out = Path(sys.argv[1])
    out.write_text(render(content))
    print(f"écrit : {out}")


def markdown_blocks() -> dict:
    """Mêmes données que la page, en Markdown, pour docs/audit-resilience/RAPPORT.md."""
    import re

    def strip(html_text):
        return re.sub(r"<[^>]+>", "", html_text).strip()

    def table(html_table):
        md = []
        for i, row in enumerate(re.findall(r"<tr>(.*?)</tr>", html_table, flags=re.S)):
            cells = [strip(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)]
            md.append("| " + " | ".join(cells) + " |")
            if i == 0:
                md.append("|" + "---|" * len(cells))
        return "\n".join(md)

    lines = ["| Domaine | Test | Panne injectée | Avant | Mesure avant | Après | Mesure après |",
             "|---|---|---|---|---|---|---|"]
    for group, sid, injection, before, after, metric in ROWS:
        b_txt, a_txt = metric()
        lines.append(f"| {group} | {sid} | {injection} | **{before or '–'}** | {b_txt} | **{after or '–'}** | {a_txt} |")
    return {"matrice": "\n".join(lines), "capacite": table(capacity_table()),
            "reprise": table(recovery_table()), "integrite": strip(integrity_card())}


def update_markdown(path: Path) -> None:
    """Remplace chaque bloc <!-- auto:nom --> … <!-- /auto --> par les valeurs mesurées."""
    import re

    blocks = markdown_blocks()
    text = path.read_text()
    new = re.sub(r"<!-- auto:(\w+) -->.*?<!-- /auto -->",
                 lambda m: f"<!-- auto:{m[1]} -->\n{blocks[m[1]]}\n<!-- /auto -->", text, flags=re.S)
    path.write_text(new)
    print(f"mis à jour : {path}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--markdown"]:
        update_markdown(Path(sys.argv[2]))
    else:
        main()
