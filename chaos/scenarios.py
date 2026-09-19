"""Scénarios de chaos rejouables à l'identique AVANT et APRÈS correction.

    python3 chaos/scenarios.py <scénario> [--label avant|apres] [--no-restore]
    python3 chaos/scenarios.py --list

Chaque scénario suit la boucle : état de référence → trafic nominal → injection → observation
→ retour à la normale → mesure (sonde, ressources) → contrôle d'intégrité → rapport JSON
(`chaos/results/<scénario>-<label>.json`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import threading
import time
from typing import Callable, Dict, List, Optional

from lab import (
    API, Probe, Sampler, Toxi, app_pids, compose, container, crash, docker, exec_backend,
    http, integrity, iso_now, lab_password, log, mock_mode, mock_reset, mock_stats, multipart, now,
    pdf_bytes, pg_connections, psql, redis_info, restarts, restore_baseline, save, tokens,
    wait_healthy,
)

SCENARIOS: Dict[str, Callable] = {}


def web_process() -> str:
    """Daphne (code d'origine) ou uvicorn (entrypoint corrigé)."""
    return "daphne" if app_pids("backend", "daphne") else "uvicorn"


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


# --------------------------------------------------------------------------- sondes métier


class ActionProbe:
    """Une action métier répétée à intervalle fixe, chaque tentative gardée avec sa preuve."""

    def __init__(self, name: str, action: Callable[[int], dict], every: float):
        self.name, self.action, self.every = name, action, every
        self.attempts: List[dict] = []
        self._stop = threading.Event()

    def start(self, t0: float):
        self.t0 = t0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def _run(self):
        i = 0
        while not self._stop.is_set():
            started = now()
            try:
                result = self.action(i)
            except Exception as exc:  # la sonde ne doit jamais s'arrêter
                result = {"status": -1, "error": str(exc)[:200]}
            result.update({"t": round(started - self.t0, 2), "latency": round(now() - started, 3)})
            self.attempts.append(result)
            i += 1
            self._stop.wait(max(0.0, self.every - (now() - started)))

    def stop(self):
        self._stop.set()
        self.thread.join(timeout=90)
        return self

    def summary(self, start: float = 0, end: float = 1e9) -> dict:
        rows = [a for a in self.attempts if start <= a["t"] < end]
        failed = [a for a in rows if not (0 < a.get("status", 0) < 500)]
        return {
            "attempts": len(rows),
            "failed": len(failed),
            "statuses": _count([a.get("status") for a in rows]),
            "max_latency_s": max((a["latency"] for a in rows), default=0),
        }


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


def login_probe() -> ActionProbe:
    emails = [f"pays{i:02d}@lab.local" for i in range(10)]
    password = lab_password()

    def action(i: int) -> dict:
        status, _, _ = http("POST", f"{API}/auth/login", timeout=30,
                            body={"email": emails[i % len(emails)], "password": password})
        return {"status": status}

    return ActionProbe("login", action, every=3.0)


def upload_probe(token: str, amms: List[str]) -> ActionProbe:
    """Téléverse un PDF unique ; `persisted` sera vérifié en base après coup (sha256)."""

    def action(i: int) -> dict:
        content = pdf_bytes(f"upload-{i}")
        body, ctype = multipart({"kind": "AUTRE", "title": f"chaos {i}"},
                                {"file": (f"chaos-{i}.pdf", content, "application/pdf")})
        amm = amms[i % len(amms)]
        status, _, _ = http("POST", f"{API}/amms/{amm}/documents", token, raw=body,
                            content_type=ctype, timeout=60)
        return {"status": status, "sha256": hashlib.sha256(content).hexdigest()}

    return ActionProbe("upload", action, every=4.0)


def renewal_probe(token: str, amms: List[str]) -> ActionProbe:
    """Écriture transactionnelle : décision obtenue (renouvellement + recalcul AMM + alertes)."""

    def action(i: int) -> dict:
        amm = amms[i % len(amms)]
        number = f"CHAOS-{int(now() * 1000)}-{i}"
        status, _, _ = http("POST", f"{API}/amms/{amm}/renewals", token, timeout=60,
                            body={"number": number, "start_date": "2026-01-15"})
        return {"status": status, "number": number}

    return ActionProbe("renewal", action, every=5.0)


def persisted_uploads(probe: ActionProbe) -> dict:
    """Croise les réponses HTTP avec la base : un 5xx dont le fichier est pourtant enregistré
    est une écriture « fantôme » que l'utilisateur va retenter."""
    shas = [a["sha256"] for a in probe.attempts if "sha256" in a]
    if not shas:
        return {}
    rows = psql("select sha256 from documents_document where sha256 in (%s)"
                % ",".join(f"'{s}'" for s in shas))
    stored = set(rows.split())
    out = {"saved_ok": 0, "saved_but_error": 0, "lost_after_error": 0, "saved_after_timeout": 0}
    for a in probe.attempts:
        if "sha256" not in a:
            continue
        saved = a["sha256"] in stored
        ok = 200 <= a["status"] < 300
        if ok and saved:
            out["saved_ok"] += 1
        elif ok and not saved:
            out.setdefault("reported_ok_but_missing", 0)
            out["reported_ok_but_missing"] += 1
        elif saved:
            out["saved_after_timeout" if a["status"] == 0 else "saved_but_error"] += 1
        else:
            out["lost_after_error"] += 1
    return out


def persisted_renewals(probe: ActionProbe) -> dict:
    numbers = [a["number"] for a in probe.attempts if "number" in a]
    if not numbers:
        return {}
    rows = psql("select number from amm_renewal where number in (%s)"
                % ",".join(f"'{n}'" for n in numbers))
    stored = set(rows.split())
    out = {"saved_ok": 0, "saved_but_error": 0, "not_saved_error": 0}
    for a in probe.attempts:
        if "number" not in a:
            continue
        saved, ok = a["number"] in stored, 200 <= a["status"] < 300
        key = "saved_ok" if ok and saved else "saved_but_error" if saved else (
            "reported_ok_but_missing" if ok else "not_saved_error")
        out[key] = out.get(key, 0) + 1
    return out


# --------------------------------------------------------------------------- canevas


def fault_run(name: str, label: str, inject: Callable, heal: Callable, *, before: float = 15,
              during: float = 60, after: float = 45, users: int = 10, restore: bool = True,
              probes: Optional[List[str]] = None, extra: Optional[Callable] = None) -> dict:
    if restore:
        restore_baseline()
    since = iso_now()
    creds = tokens(1, "CEO_ADMIN")[0]
    sampler = Sampler().start()
    probe = Probe(users=users, think=0.5).start()
    actions: List[ActionProbe] = []
    for kind in probes or ["login", "upload", "renewal"]:
        if kind == "login":
            actions.append(login_probe())
        elif kind == "upload":
            actions.append(upload_probe(creds["token"], creds["amms"][:30]))
        elif kind == "renewal":
            actions.append(renewal_probe(creds["token"], creds["amms"][30:60]))
    for action in actions:
        action.start(probe.t0)
    health: List[tuple] = []
    stop_health = threading.Event()

    def watch_health():
        while not stop_health.is_set():
            code, lat, _ = http("GET", API + "/health", timeout=5)
            health.append((round(now() - probe.t0, 1), code, round(lat, 2)))
            stop_health.wait(1)

    threading.Thread(target=watch_health, daemon=True).start()

    time.sleep(before)
    t_inject = now() - probe.t0
    probe.mark(f"injection : {name}")
    injected = inject() or {}
    time.sleep(during)
    t_heal = now() - probe.t0
    probe.mark("retour à la normale")
    heal()
    time.sleep(after)
    extra_data = extra() if extra else {}
    stop_health.set()
    probe.stop()
    for action in actions:
        action.stop()
    resources = sampler.stop()

    # récupération : première seconde après le retour à la normale où la santé et la sonde sont OK
    recovered_at = None
    for t, code, _ in health:
        if t >= t_heal and code == 200:
            later = [s for s in probe.samples if s.t >= t and not Probe.ok(s)]
            if not later or all(s.t < t for s in later):
                recovered_at = t
                break
    phases = {
        "avant": probe.window(0, t_inject),
        "pendant": probe.window(t_inject, t_heal),
        "apres": probe.window(t_heal, 1e9),
    }
    per_kind = {kind: {ph: probe.window(a, b, kind) for ph, (a, b) in {
        "avant": (0, t_inject), "pendant": (t_inject, t_heal), "apres": (t_heal, 1e9)}.items()}
        for kind in ("list", "detail", "analytics", "alerts", "write", "me")}
    result = {
        "scenario": name,
        "label": label,
        "injected_at_s": round(t_inject, 1),
        "healed_at_s": round(t_heal, 1),
        "injection": injected,
        "phases": phases,
        "per_kind": per_kind,
        "outage": probe.outage(t_inject),
        "recovered_s_after_heal": round(recovered_at - t_heal, 1) if recovered_at else None,
        "health": {
            "during": _count([c for t, c, _ in health if t_inject <= t < t_heal]),
            "max_latency_s": max((lat for _, _, lat in health), default=0),
        },
        "actions": {a.name: {"pendant": a.summary(t_inject, t_heal), "apres": a.summary(t_heal)}
                    for a in actions},
        "timeline": probe.timeline(5),
        "resources": _resource_peaks(resources),
        "extra": extra_data,
    }
    for action in actions:
        if action.name == "upload":
            result["actions"]["upload"]["persistence"] = persisted_uploads(action)
        if action.name == "renewal":
            result["actions"]["renewal"]["persistence"] = persisted_renewals(action)
    result["integrity"] = integrity(since)
    save(f"{name}-{label}", result)
    _print_summary(result)
    return result


def _resource_peaks(rows: List[dict]) -> dict:
    peaks: dict = {}
    for row in rows:
        for key, value in row.items():
            if key.endswith("_cpu"):
                peaks[key] = max(peaks.get(key, 0), value)
            if key.endswith("_mem"):
                peaks[key] = value  # dernier relevé
        pg = row.get("pg") or {}
        total = sum(pg.values())
        peaks["pg_connections_max"] = max(peaks.get("pg_connections_max", 0), total)
        peaks["pg_idle_in_tx_max"] = max(peaks.get("pg_idle_in_tx_max", 0),
                                         pg.get("idle in transaction", 0))
    return peaks


def _print_summary(r: dict):
    p = r["phases"]
    log(f"== {r['scenario']} [{r['label']}]")
    for phase in ("avant", "pendant", "apres"):
        w = p[phase]
        if w.get("requests"):
            log(f"   {phase:8} req={w['requests']:5} err={w['errors']:4} "
                f"p50={w['p50_ms']}ms p95={w['p95_ms']}ms max={w['max_ms']}ms {w['statuses']}")
    for kind, phases in r["per_kind"].items():
        w = phases["pendant"]
        if w.get("requests"):
            log(f"   pendant/{kind:9} err={w['errors']}/{w['requests']} p95={w['p95_ms']}ms "
                f"max={w['max_ms']}ms {w['statuses']}")
    for name, a in r["actions"].items():
        log(f"   action {name}: pendant {a['pendant']} | après {a['apres']['statuses']}"
            + (f" | persistance {a.get('persistence')}" if a.get("persistence") else ""))
    log(f"   panne vue : {r['outage']} ; récupération {r['recovered_s_after_heal']} s ; "
        f"santé pendant {r['health']['during']}")
    log(f"   ressources {r['resources']}")
    log(f"   intégrité {r['integrity']}")


# --------------------------------------------------------------------------- S03 Redis


@scenario
def s03a_redis_kill(label: str, restore: bool = True):
    """Redis tué (SIGKILL) 60 s pendant le trafic, puis redémarré."""
    return fault_run(
        "s03a_redis_kill", label,
        inject=lambda: docker("kill", container("redis")) and {"how": "docker kill redis"},
        heal=lambda: docker("start", container("redis")),
        restore=restore,
    )


@scenario
def s03b_redis_hang(label: str, restore: bool = True):
    """Redis figé : connexions acceptées, aucune réponse (toxiproxy timeout=0), 60 s."""
    return fault_run(
        "s03b_redis_hang", label,
        inject=lambda: Toxi.timeout("redis") and {"how": "toxiproxy timeout redis"},
        heal=lambda: Toxi.clear("redis"),
        restore=restore,
    )


@scenario
def s03c_redis_hang_load(label: str, restore: bool = True):
    """Redis figé 60 s sous 40 utilisateurs : la saturation gagne-t-elle les lectures ?"""
    return fault_run(
        "s03c_redis_hang_load", label,
        inject=lambda: Toxi.timeout("redis") and {"how": "toxiproxy timeout redis", "users": 40},
        heal=lambda: Toxi.clear("redis"),
        users=40, restore=restore,
    )


@scenario
def s04_redis_latency(label: str, restore: bool = True):
    """Échelle de latence Redis : 100 ms, 500 ms, 1 s, 3 s (écritures dans des transactions)."""
    out = {}
    for ms in (100, 500, 1000, 3000):
        out[ms] = fault_run(
            f"s04_redis_latency_{ms}", label,
            inject=lambda ms=ms: Toxi.latency("redis", ms) and {"latency_ms": ms},
            heal=lambda: Toxi.clear("redis"),
            during=40, after=20, restore=restore, probes=["login", "renewal"],
        )
        restore = False
    return out


# --------------------------------------------------------------------------- S02 PostgreSQL


@scenario
def s02a_pg_kill(label: str, restore: bool = True):
    """PostgreSQL tué (SIGKILL) 30 s sous trafic, puis redémarré."""
    return fault_run(
        "s02a_pg_kill", label,
        inject=lambda: docker("kill", container("postgres")) and {"how": "docker kill postgres"},
        heal=lambda: docker("start", container("postgres")),
        during=30, after=60, restore=restore,
    )


@scenario
def s02f_pg_quick_restart(label: str, restore: bool = True):
    """PostgreSQL redémarré (arrêt rapide, retour en ~2 s) : le pool sert-il des connexions mortes ?"""
    return fault_run(
        "s02f_pg_quick_restart", label,
        inject=lambda: compose("restart", "-t", "1", "postgres") and {"how": "docker restart postgres"},
        heal=lambda: None, during=5, after=40, restore=restore, probes=["renewal"],
    )


@scenario
def s02b_pg_hang(label: str, restore: bool = True):
    """PostgreSQL figé (docker pause : TCP accepté, aucune réponse) 60 s, puis repris."""
    return fault_run(
        "s02b_pg_hang", label,
        inject=lambda: docker("pause", container("postgres")) and {"how": "docker pause postgres"},
        heal=lambda: docker("unpause", container("postgres")),
        during=60, after=60, restore=restore,
    )


@scenario
def s02c_pg_latency(label: str, restore: bool = True):
    """Échelle de latence PostgreSQL : 100 ms, 500 ms, 1 s, 3 s par aller-retour."""
    out = {}
    for ms in (100, 500, 1000, 3000):
        out[ms] = fault_run(
            f"s02c_pg_latency_{ms}", label,
            inject=lambda ms=ms: Toxi.latency("postgres", ms) and {"latency_ms": ms},
            heal=lambda: Toxi.clear("postgres"),
            during=40, after=30, restore=restore, probes=["renewal"],
        )
        restore = False
    return out


@scenario
def s02d_pg_reset_mid_tx(label: str, restore: bool = True):
    """Connexions PostgreSQL coupées (RST) au hasard pendant 60 s d'écritures intensives."""
    stop = threading.Event()
    cuts = {"n": 0}

    def flapper():
        while not stop.is_set():
            try:
                Toxi.reset_peer("postgres")
                cuts["n"] += 1
                time.sleep(random.uniform(0.05, 0.3))
                Toxi.clear("postgres")
            except Exception:
                pass
            stop.wait(random.uniform(0.3, 1.5))

    def inject():
        threading.Thread(target=flapper, daemon=True).start()
        return {"how": "reset_peer intermittent"}

    def heal():
        stop.set()
        time.sleep(0.5)
        Toxi.clear("postgres")

    result = fault_run("s02d_pg_reset_mid_tx", label, inject=inject, heal=heal, users=20,
                       during=60, after=30, restore=restore, extra=lambda: {"cuts": cuts["n"]})
    return result


POOL_BURST = 300


@scenario
def s02e_pg_pool_saturation(label: str, restore: bool = True):
    """Pool saturé : 300 requêtes simultanées rendues lentes (PostgreSQL +200 ms/aller-retour)."""
    if restore:
        restore_baseline()
    since = iso_now()
    creds = tokens(40)
    # Pool réchauffé de la même façon pour les deux versions : la sonde /health d'origine passait
    # par le pool et le gardait ouvert, la nouvelle non ; à froid, la comparaison mesurait surtout
    # la croissance du pool à +200 ms par aller-retour (sur 150 requêtes : 68 réussites contre
    # 88 à 98 ; pool chaud : 150 sur 150 des deux côtés, d'où 300 requêtes pour saturer).
    burst(40, lambda i: http("GET", f"{API}/amms?page=1", creds[i]["token"], timeout=30))
    Toxi.latency("postgres", 200)
    results, lock = [], threading.Lock()

    def worker(i):
        cred = creds[i % len(creds)]
        status, lat, body = http("GET", f"{API}/amms?page={1 + i % 5}", cred["token"], timeout=60)
        with lock:
            results.append((status, lat, body[:120].decode(errors="replace") if status >= 500 else ""))

    sampler = Sampler(every=1).start()
    started = now()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(POOL_BURST)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    burst_s = now() - started
    Toxi.clear("postgres")
    time.sleep(3)
    after = [http("GET", f"{API}/amms", creds[0]["token"], timeout=10)[0] for _ in range(5)]
    lat = sorted(r[1] for r in results)
    from lab import pct
    out = {
        "scenario": "s02e_pg_pool_saturation", "label": label, "concurrent": POOL_BURST,
        "burst_duration_s": round(burst_s, 1),
        "statuses": _count(r[0] for r in results),
        "p50_s": round(pct(lat, 50), 2), "p95_s": round(pct(lat, 95), 2), "max_s": round(lat[-1], 2),
        "error_bodies": list({r[2] for r in results if r[2]})[:3],
        "after_statuses": after,
        "resources": _resource_peaks(sampler.stop()),
        "integrity": integrity(since),
    }
    save(f"s02e_pg_pool_saturation-{label}", out)
    log(json.dumps({k: v for k, v in out.items() if k != "integrity"}, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- S01 / S11 processus


@scenario
def s01_backend_crash(label: str, restore: bool = True):
    """Processus web tué (SIGKILL) 4 fois pendant lectures, écritures, transactions et uploads."""
    kills = []

    def inject():
        for _ in range(4):
            kills.append({"t": round(now(), 1), "pids": crash("backend", web_process())})
            time.sleep(15)
        return {"kills": len(kills)}

    def extra():
        return {"restart_count": restarts("backend"),
                "orphan_blobs_check": "voir integrity.orphan_blobs"}

    return fault_run("s01_backend_crash", label, inject=inject, heal=lambda: None, users=20,
                     during=5, after=30, restore=restore, extra=extra)


@scenario
def s11a_backend_sigterm(label: str, restore: bool = True):
    """Arrêt propre (SIGTERM) du web pendant des requêtes longues : sont-elles terminées ?"""
    return _signal_inflight("s11a_backend_sigterm", "TERM", label, restore)


@scenario
def s11b_backend_sigkill(label: str, restore: bool = True):
    """Même test en SIGKILL, pour comparaison."""
    return _signal_inflight("s11b_backend_sigkill", "KILL", label, restore)


def _signal_inflight(name: str, sig: str, label: str, restore: bool):
    if restore:
        restore_baseline()
    creds = tokens(20)
    Toxi.latency("postgres", 300)  # requêtes de ~2-4 s : il y en a toujours en vol
    results, lock = [], threading.Lock()

    def worker(i):
        cred = creds[i % len(creds)]
        amm = cred["amms"][i % len(cred["amms"])]
        if i % 2:
            r = http("PATCH", f"{API}/amms/{amm}", cred["token"], body={"notes": f"{name} {i}"}, timeout=60)
        else:
            r = http("GET", f"{API}/amms?page=2", cred["token"], timeout=60)
        with lock:
            results.append(r[0])

    since = iso_now()
    ip = lambda: docker("inspect", container("backend"), "--format",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", check=False).strip()
    ip_before = ip()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    time.sleep(1.5)
    t0 = now()
    pids = crash("backend", web_process(), sig)
    for t in threads:
        t.join()
    Toxi.clear("postgres")
    diag = []
    for _ in range(60):  # 60 s d'observation, chaque seconde : processus, conteneur, santé
        state = docker("inspect", container("backend"), "--format",
                       "{{.State.Status}} restarts={{.RestartCount}} exit={{.State.ExitCode}}", check=False).strip()
        direct = http("GET", "http://localhost:19800/api/v1/health", timeout=3)[0]
        proxied = http("GET", API + "/health", timeout=3)[0]
        diag.append({"t": round(now() - t0, 1), "container": state, "direct": direct, "via_nginx": proxied,
                     "ip": ip(), "procs": app_pids("backend", web_process()) if "running" in state else []})
        if direct == 200 and proxied == 200:
            break
        time.sleep(1)
    back_s = None
    try:
        wait_healthy(timeout=120)
        back_s = round(now() - t0, 1)
    except TimeoutError:
        pass
    logs = docker("logs", "--since", "3m", container("backend"), check=False).splitlines()
    first_ok = next((d["t"] for d in diag if d["direct"] == 200 and d["via_nginx"] == 200), None)
    out = {"scenario": name, "label": label, "signal": sig, "pids": pids,
           "inflight_statuses": _count(results), "back_after_s": first_ok or back_s,
           "ip_before": ip_before, "diagnostic": diag,
           "backend_log_tail": [l[:200] for l in logs if "HTTP" not in l][-12:],
           "integrity": integrity(since)}
    save(f"{name}-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


@scenario
def s11c_nginx_restart_without_grafana(label: str, restore: bool = False):
    """Grafana arrêté puis nginx redémarré : l'API reste-t-elle joignable ?"""
    compose("stop", "grafana")
    crash_t = now()
    compose("restart", "nginx")
    time.sleep(8)
    code, _, _ = http("GET", API + "/health", timeout=5)
    state = docker("inspect", container("nginx"), "--format",
                   "{{.State.Status}} restarts={{.RestartCount}}").strip()
    logs = docker("logs", "--tail", "5", container("nginx"), check=False)
    compose("start", "grafana")
    time.sleep(3)
    compose("restart", "nginx")
    back = wait_healthy()
    out = {"scenario": "s11c_nginx_restart_without_grafana", "label": label,
           "api_status_with_grafana_down": code, "nginx_state": state,
           "nginx_log": [l for l in logs.splitlines() if "emerg" in l or "error" in l][-3:],
           "api_back_after_grafana_start_s": round(back, 1)}
    save(f"s11c_nginx_restart_without_grafana-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- S10 stockage


@scenario
def s10a_storage_down(label: str, restore: bool = True):
    """MinIO arrêté 60 s : uploads, téléchargements, et tout le reste."""
    def extra():
        creds = tokens(1, "CEO_ADMIN")[0]
        doc = psql("select id from documents_document order by uploaded_at limit 1").strip()
        return {"download_after": http("GET", f"{API}/documents/{doc}/file", creds["token"])[0]}

    return fault_run(
        "s10a_storage_down", label,
        inject=lambda: docker("kill", container("minio")) and {"how": "docker kill minio"},
        heal=lambda: docker("start", container("minio")),
        restore=restore, extra=extra, probes=["upload", "renewal"],
    )


@scenario
def s10b_storage_hang(label: str, restore: bool = True):
    """Stockage figé (toxiproxy timeout) 60 s sous 30 utilisateurs, avec uploads."""
    return fault_run(
        "s10b_storage_hang", label,
        inject=lambda: Toxi.timeout("minio") and {"how": "toxiproxy timeout minio"},
        heal=lambda: Toxi.clear("minio"),
        users=30, restore=restore, probes=["upload", "renewal"],
    )


@scenario
def s10c_storage_downloads(label: str, restore: bool = True):
    """Téléchargements concurrents pendant une panne de stockage : 20 lecteurs de scans."""
    if restore:
        restore_baseline()
    creds = tokens(1, "CEO_ADMIN")[0]
    docs = psql("select id from documents_document limit 40").split()
    docker("kill", container("minio"))
    results, lock = [], threading.Lock()

    def reader(doc):
        r = http("GET", f"{API}/documents/{doc}/file", creds["token"], timeout=90)
        with lock:
            results.append((r[0], round(r[1], 1)))

    threads = [threading.Thread(target=reader, args=(d,)) for d in docs[:20]]
    for t in threads:
        t.start()
    time.sleep(2)
    side = [http("GET", f"{API}/amms?page=1", creds["token"], timeout=30)[:2] for _ in range(5)]
    for t in threads:
        t.join()
    docker("start", container("minio"))
    out = {"scenario": "s10c_storage_downloads", "label": label,
           "download_statuses": _count(r[0] for r in results),
           "download_latency_max_s": max(r[1] for r in results),
           "unrelated_list_during": [(c, round(l, 2)) for c, l in side]}
    save(f"s10c_storage_downloads-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- S12 / S13 worker et e-mails


def enqueue_emails(n: int, tag: str) -> List[str]:
    """Crée n notifications e-mail et publie leur envoi, comme le fait `dispatch()`."""
    out = exec_backend(
        "import json\n"
        "from apps.accounts.models import User\n"
        "from apps.notifications.models import Notification\n"
        "from apps.notifications.tasks import send_alert_email\n"
        "u=User.objects.get(email='ceo@amm.local')\n"
        "ids=[]\n"
        f"for i in range({n}):\n"
        f"    x=Notification.objects.create(user=u, channel='EMAIL', title='chaos {tag} '+str(i), body='corps', link='http://lab')\n"
        "    send_alert_email.delay(str(x.pk)); ids.append(str(x.pk))\n"
        "print(json.dumps(ids))"
    )
    return json.loads(out.strip().splitlines()[-1])


def email_state(tag: str) -> dict:
    row = psql(
        "select count(*), count(sent_at) from notifications_notification "
        f"where title like 'chaos {tag} %'"
    ).strip().split("|")
    return {"created": int(row[0]), "marked_sent": int(row[1])}


def upload_docs(token: str, amms: List[str], n: int, tag: str) -> List[str]:
    ids = []
    for i in range(n):
        body, ctype = multipart({"kind": "AUTRE"}, {"file": (f"{tag}-{i}.pdf", pdf_bytes(f"{tag}{i}"), "application/pdf")})
        status, _, payload = http("POST", f"{API}/amms/{amms[i % len(amms)]}/documents", token,
                                  raw=body, content_type=ctype, timeout=60)
        if status == 201:
            ids.append(json.loads(payload)["id"])
    return ids


def previews_done(ids: List[str]) -> int:
    if not ids:
        return 0
    return int(psql("select count(*) from documents_document where page_count is not null and id in (%s)"
                    % ",".join(f"'{i}'" for i in ids)).strip())


def upload_dossier(token: str, tag: str, files: int = 3) -> dict:
    """Dossier de vrais PDF scannés (chaos/fixtures, générés par gen_fixtures.py)."""
    from lab import HERE
    root = f"dossier-{tag}"
    scans = sorted((HERE / "fixtures").glob("scan*.pdf"))
    specs = [(f"page{i}.pdf", scans[i % len(scans)].read_bytes(), "application/pdf") for i in range(files)]
    body, ctype = multipart(
        {"root_name": root, "paths": json.dumps([f"{root}/{name}" for name, _, _ in specs])},
        {"files": specs},
    )
    status, _, payload = http("POST", f"{API}/dossier-imports", token, raw=body, content_type=ctype, timeout=120)
    return {"status": status, **(json.loads(payload) if status == 202 else {"body": payload[:200].decode(errors="replace")})}


def dossier_status(pk: str) -> str:
    return psql(f"select status from imports_dossierimport where id='{pk}'").strip()


def wait_until(predicate: Callable[[], bool], timeout: float, every: float = 2) -> Optional[float]:
    started = now()
    while now() - started < timeout:
        if predicate():
            return round(now() - started, 1)
        time.sleep(every)
    return None


@scenario
def s12a_worker_down(label: str, restore: bool = True):
    """Worker arrêté 60 s pendant que des tâches arrivent (e-mails, aperçus, analyse) ; tout
    est-il exécuté, une seule fois, au redémarrage ?"""
    if restore:
        restore_baseline()
    since = iso_now()
    mock_reset()
    ceo = tokens(1, "CEO_ADMIN")[0]
    compose("stop", "worker")
    ids = enqueue_emails(20, "s12a")
    docs = upload_docs(ceo["token"], ceo["amms"], 10, "s12a")
    dossier = upload_dossier(ceo["token"], "s12a")
    queued = redis_info()["celery_queue"]
    time.sleep(60)
    t0 = now()
    compose("start", "worker")
    done = wait_until(lambda: email_state("s12a")["marked_sent"] == 20 and previews_done(docs) == len(docs)
                      and dossier_status(dossier.get("id", "")) not in ("PENDING", "RUNNING"), 240)
    stats = mock_stats()
    out = {
        "scenario": "s12a_worker_down", "label": label, "queued_while_down": queued,
        "drained_after_restart_s": done, "emails": email_state("s12a"),
        "gmail_messages_received": stats["messages"], "gmail_token_calls": stats["token"],
        "previews": f"{previews_done(docs)}/{len(docs)}",
        "dossier": {"upload": dossier.get("status"), "final": dossier_status(dossier.get("id", ""))},
        "integrity": integrity(since),
    }
    save(f"s12a_worker_down-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


@scenario
def s12b_worker_kill_mid_task(label: str, restore: bool = True):
    """Worker tué (SIGKILL) pendant des envois d'e-mails lents et une analyse de dossier."""
    if restore:
        restore_baseline()
    since = iso_now()
    mock_reset()
    ceo = tokens(1, "CEO_ADMIN")[0]
    mock_mode("slow", 12)
    Toxi.latency("minio", 1500)  # l'analyse lit ses fichiers sur S3 : elle dure
    dossier = upload_dossier(ceo["token"], "s12b", files=4)
    ids = enqueue_emails(6, "s12b")
    running = wait_until(lambda: dossier_status(dossier.get("id", "")) == "RUNNING", 30, 0.5)
    time.sleep(3)
    before = {"dossier": dossier_status(dossier.get("id", "")), "mock": mock_stats()}
    pids = crash("worker", "celery")
    mock_mode("ok")
    Toxi.clear("minio")
    wait_until(lambda: restarts("worker") > 0, 30, 1)
    time.sleep(90)  # redémarrage, puis traitement de ce qui reste
    state_90s = {"dossier": dossier_status(dossier.get("id", "")), "emails": email_state("s12b")}
    # messages réservés par le worker tué : ils ne reviennent qu'après visibility_timeout
    unacked = compose("exec", "-T", "redis", "redis-cli", "hlen", "unacked").strip()
    queue = compose("exec", "-T", "redis", "redis-cli", "llen", "celery").strip()
    # Avance rapide (identique avant/après) : on vieillit de 30 min les horodatages au lieu
    # d'attendre, puis un passage du rattrapage s'il existe (code d'origine : aucun).
    psql(f"update imports_dossierimport set created_at=created_at - interval '30 minutes' where id='{dossier.get('id')}'")
    try:  # colonne absente du code d'origine
        psql("update imports_dossierimport set started_at=started_at - interval '30 minutes' "
             f"where id='{dossier.get('id')}'")
    except RuntimeError:
        pass
    psql("update notifications_notification set created_at=created_at - interval '30 minutes' "
         "where title like 'chaos s12b %'")
    try:
        psql("update notifications_notification set last_attempt_at=last_attempt_at - "
             "interval '30 minutes' where title like 'chaos s12b %'")
    except RuntimeError:
        pass
    sweep = exec_backend(
        "try:\n"
        "    from apps.core.tasks import recover_pending_work\n"
        "    print(recover_pending_work())\n"
        "except ImportError:\n"
        "    print('pas de rattrapage')", service="worker")
    time.sleep(30)
    relaunch = http("POST", f"{API}/dossier-imports/{dossier.get('id')}/analyze", ceo["token"], body={}, timeout=30)
    relaunched_final = wait_until(lambda: dossier_status(dossier.get("id", "")) in ("READY", "FAILED"), 120, 3)
    stats = mock_stats()
    out = {
        "scenario": "s12b_worker_kill_mid_task", "label": label, "killed_pids": pids,
        "dossier_running_before_kill": running is not None, "state_before_kill": before["dossier"],
        "after_restart_90s": state_90s,
        "sweeper": sweep.strip().splitlines()[-1][:300] if sweep.strip() else "",
        "dossier_relaunch": {"status": relaunch[0], "body": relaunch[2][:160].decode(errors="replace")},
        "dossier_after_relaunch": dossier_status(dossier.get("id", "")), "relaunch_done_s": relaunched_final,
        "emails": email_state("s12b"),
        "gmail_messages_received": stats["messages"],
        "redis_unacked_after_restart": unacked, "redis_queue_after_restart": queue,
        "integrity": integrity(since),
    }
    save(f"s12b_worker_kill_mid_task-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


@scenario
def s13_gmail_failures(label: str, restore: bool = True):
    """API Gmail : 500, 429, réponse invalide, lente, figée, coupée, accusé perdu (60 s chacun),
    puis indisponible 3 min ; e-mails finalement envoyés ? doublons ? tâches voisines bloquées ?"""
    if restore:
        restore_baseline()
    since = iso_now()
    ceo = tokens(1, "CEO_ADMIN")[0]
    report = {}
    for mode, delay in (("http500", 0), ("http429", 0), ("invalid", 0), ("slow", 30),
                        ("hang", 0), ("down", 0), ("ack_lost", 0)):
        mock_reset()
        mock_mode(mode, delay)
        tag = f"s13{mode}"
        enqueue_emails(5, tag)
        time.sleep(2)
        docs = upload_docs(ceo["token"], ceo["amms"], 3, tag)
        t0 = now()
        preview = wait_until(lambda: previews_done(docs) == len(docs), 60, 1)
        time.sleep(max(0, 60 - (now() - t0)))
        during = mock_stats()
        mock_mode("ok")
        time.sleep(45)
        stats = mock_stats()
        report[mode] = {
            "attempts_during": during["requests"], "token_calls": stats["token"],
            "emails": email_state(tag), "gmail_messages_received": stats["messages"],
            "preview_latency_s": preview, "previews": f"{previews_done(docs)}/{len(docs)}",
        }
        log(f"   {mode}: {report[mode]}")
    # panne longue : 3 minutes d'erreurs 500, puis retour
    mock_reset()
    mock_mode("http500")
    enqueue_emails(5, "s13long")
    time.sleep(180)
    mock_mode("ok")
    time.sleep(60)
    report["outage_3min"] = {"emails": email_state("s13long"), "gmail_messages_received": mock_stats()["messages"]}
    log(f"   outage_3min: {report['outage_3min']}")
    # Avance rapide identique avant/après : les relances ne sont plus immédiates, on vieillit de
    # 30 min les e-mails non partis puis un passage du rattrapage (s'il existe) ; Gmail est rétabli.
    received_before = mock_stats()["messages"]
    psql("update notifications_notification set created_at=created_at - interval '30 minutes' "
         "where title like 'chaos s13%' and sent_at is null")
    try:
        psql("update notifications_notification set last_attempt_at=last_attempt_at - interval "
             "'30 minutes' where title like 'chaos s13%' and sent_at is null")
    except RuntimeError:
        pass
    sweep = exec_backend(
        "try:\n    from apps.core.tasks import recover_pending_work\n    print(recover_pending_work())\n"
        "except ImportError:\n    print('pas de rattrapage')", service="worker")
    time.sleep(45)
    final = psql("select count(*), count(sent_at) from notifications_notification "
                 "where title like 'chaos s13%'").strip().split("|")
    report["after_sweep"] = {
        "sweeper": sweep.strip().splitlines()[-1][-160:],
        "emails_total": int(final[0]), "emails_sent": int(final[1]),
        "outage_3min_sent": email_state("s13long")["marked_sent"],
        "outage_3min_extra_messages": mock_stats()["messages"] - received_before,
    }
    log(f"   après rattrapage : {report['after_sweep']}")
    out = {"scenario": "s13_gmail_failures", "label": label, "modes": report,
           "integrity": integrity(since)}
    save(f"s13_gmail_failures-{label}", out)
    return out


# --------------------------------------------------------------------------- S15 concurrence


def burst(n: int, fn: Callable[[int], tuple]) -> List[tuple]:
    results, lock = [], threading.Lock()
    gate = threading.Barrier(n)

    def run(i):
        gate.wait()
        r = fn(i)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@scenario
def s15_concurrency(label: str, restore: bool = True):
    """Même ressource, requêtes simultanées : doublons, courses, mises à jour perdues."""
    if restore:
        restore_baseline()
    since = iso_now()
    ceo = tokens(1, "CEO_ADMIN")[0]
    tok = ceo["token"]
    amms = ceo["amms"]
    out = {"scenario": "s15_concurrency", "label": label}

    # a) la même décision envoyée 10 fois (double clic, relance réseau)
    amm = amms[1]
    r = burst(10, lambda i: http("POST", f"{API}/amms/{amm}/renewals", tok,
                                 body={"number": "DUP-2026-001", "start_date": "2026-02-01"})[0:1])
    stored = int(psql(f"select count(*) from amm_renewal where amm_id='{amm}' and number='DUP-2026-001'"))
    out["a_same_decision_x10"] = {"statuses": _count(x[0] for x in r), "renewals_created": stored}

    # b) 20 planifications simultanées : un seul renouvellement ouvert autorisé
    amm = amms[2]
    r = burst(20, lambda i: http("POST", f"{API}/amms/{amm}/renewals", tok, body={"notes": f"plan {i}"})[0:1])
    opened = int(psql(f"select count(*) from amm_renewal where amm_id='{amm}' and workflow_status in "
                      "('PLANIFIE','EN_PREPARATION','DEPOSE','EN_INSTRUCTION')"))
    out["b_plan_x20"] = {"statuses": _count(x[0] for x in r), "open_renewals": opened}

    # c) mises à jour perdues : deux éditeurs sur deux champs différents de la même AMM
    amm = amms[3]
    last = {}

    def editor(field, n):
        for i in range(n):
            status = http("PATCH", f"{API}/amms/{amm}", tok, body={field: f"{field}-{i}"})[0]
            if status == 200:
                last[field] = f"{field}-{i}"

    ta = threading.Thread(target=editor, args=("notes", 60))
    tb = threading.Thread(target=editor, args=("holder", 60))
    ta.start(); tb.start(); ta.join(); tb.join()
    final = psql(f"select notes || '|' || holder from amm_marketingauthorization where id='{amm}'").strip()
    regress = psql(
        "select count(*) from (select notes, holder, lag(notes) over w pn, lag(holder) over w ph "
        f"from amm_historicalmarketingauthorization where id='{amm}' window w as (order by history_date, history_id)) h "
        "where (pn like 'notes-%' and notes like 'notes-%' and split_part(notes,'-',2)::int < split_part(pn,'-',2)::int) "
        "or (ph like 'holder-%' and holder like 'holder-%' and split_part(holder,'-',2)::int < split_part(ph,'-',2)::int)"
    ).strip()
    out["c_lost_update"] = {"expected": f"{last.get('notes')}|{last.get('holder')}", "final": final,
                            "lost": final != f"{last.get('notes')}|{last.get('holder')}",
                            "history_regressions": int(regress)}

    # d) décision obtenue pendant qu'un autre modifie l'AMM : statut calculé périmé ?
    amm = amms[4]
    for i in range(15):
        burst(2, lambda k, i=i: http("POST", f"{API}/amms/{amm}/renewals", tok,
                                     body={"number": f"RACE-{i}", "start_date": "2026-03-01"})[0:1]
              if k == 0 else http("PATCH", f"{API}/amms/{amm}", tok, body={"notes": f"race {i}"})[0:1])

    # e) remplacement concurrent du même document courant
    doc = psql("select id from documents_document where is_current and archived_at is null "
               "order by uploaded_at limit 1").strip()

    def replace(i):
        body, ctype = multipart({}, {"file": (f"v{i}.pdf", pdf_bytes(f"replace{i}"), "application/pdf")})
        return http("POST", f"{API}/documents/{doc}/replace", tok, raw=body, content_type=ctype)[0:1]

    r = burst(8, replace)
    successors = int(psql(f"select count(*) from documents_document where replaces_id='{doc}' "
                          "and is_current and archived_at is null"))
    out["e_replace_x8"] = {"statuses": _count(x[0] for x in r), "current_successors": successors}

    # f) le même fichier envoyé 20 fois en même temps
    content = pdf_bytes("same-file")
    amm = amms[5]

    def same(i):
        body, ctype = multipart({"kind": "AUTRE"}, {"file": ("same.pdf", content, "application/pdf")})
        return http("POST", f"{API}/amms/{amm}/documents", tok, raw=body, content_type=ctype)[0:1]

    r = burst(20, same)
    sha = hashlib.sha256(content).hexdigest()
    out["f_same_file_x20"] = {"statuses": _count(x[0] for x in r),
                              "stored": int(psql(f"select count(*) from documents_document where sha256='{sha}'"))}

    # g) transitions contradictoires simultanées sur un même dépôt
    renewal = psql("select id from amm_renewal where workflow_status='DEPOSE' limit 1").strip()
    targets = ["EN_INSTRUCTION", "ABANDONNE", "OBTENU"]
    r = burst(12, lambda i: http("POST", f"{API}/renewals/{renewal}/transition", tok,
                                 body={"to": targets[i % 3], "number": f"T{i}", "start_date": "2026-04-01"})[0:1])
    out["g_transitions_x12"] = {"statuses": _count(x[0] for x in r),
                                "final": psql(f"select workflow_status from amm_renewal where id='{renewal}'").strip()}

    out["integrity"] = integrity(since)
    save(f"s15_concurrency-{label}", out)
    log(json.dumps(out, ensure_ascii=False, indent=1))
    return out


# --------------------------------------------------------------------------- S05 / S06 charge


def k6(args: List[str], tag: str, timeout: int = 900) -> dict:
    """Lance k6 dans le réseau du labo (pas de biais de redirection de port macOS)."""
    from lab import HERE, RESULTS
    (RESULTS / "tokens.json").write_text(json.dumps(tokens(200)))
    summary = f"/data/results/k6-{tag}.json"
    docker("run", "--rm", "--network", "amm-lab_lab", "-v", f"{HERE}:/data", "grafana/k6:1.3.0",
           "run", "--quiet", "--summary-export", summary, *args, "/data/k6/users.js",
           check=False, timeout=timeout)
    data = json.loads((RESULTS / f"k6-{tag}.json").read_text())
    m = data["metrics"]

    def trend(name):
        t = m.get(name, {})
        return {k: round(t.get(k, 0)) for k in ("med", "p(95)", "p(99)", "max")} if t else {}

    reqs = m["http_reqs"]["count"]
    errors = m.get("server_errors", {}).get("count", 0)
    return {
        "requests": reqs, "rps": round(m["http_reqs"]["rate"], 1),
        "error_rate": round(errors / reqs, 4) if reqs else None, "server_errors": errors,
        "latency_ms": trend("http_req_duration"),
        "by_kind_ms": {k: trend(f"t_{k}") for k in ("list", "detail", "analytics", "alerts", "unread", "write")},
        "vus_max": m.get("vus_max", {}).get("value"),
    }


def pg_top_queries(n: int = 8) -> List[str]:
    out = psql(
        "select round(mean_exec_time::numeric,1)||' ms | '||calls||' appels | '||"
        "round(total_exec_time::numeric)||' ms total | '||left(regexp_replace(query,'\\s+',' ','g'),140) "
        f"from pg_stat_statements where dbid=(select oid from pg_database where datname='amm') "
        f"order by total_exec_time desc limit {n}"
    )
    return [line for line in out.splitlines() if line.strip()]


@scenario
def s05_load_steps(label: str, restore: bool = True):
    """Paliers 10 → 30 → 100 → 250 → 500 → 1000 utilisateurs (60 s chacun)."""
    if restore:
        restore_baseline()
    since = iso_now()
    steps = {}
    for vus in (10, 30, 100, 250, 500, 1000):
        psql("select pg_stat_statements_reset()")
        sampler = Sampler(every=2).start()
        result = k6(["-e", f"VUS={vus}", "-e", "DURATION=60s"], f"{label}-{vus}")
        rows = sampler.stop()
        result["resources"] = _resource_peaks(rows)
        result["redis"] = redis_info()
        result["top_sql"] = pg_top_queries(5)
        steps[vus] = result
        log(f"   {vus:5} VU : {result['rps']} req/s, erreurs {result['error_rate']}, "
            f"p50 {result['latency_ms'].get('med')} p95 {result['latency_ms'].get('p(95)')} "
            f"p99 {result['latency_ms'].get('p(99)')} ms | CPU web {result['resources'].get('backend_cpu')} % "
            f"PG {result['resources'].get('postgres_cpu')} % | conn PG {result['resources'].get('pg_connections_max')}")
        time.sleep(10)
    out = {"scenario": "s05_load_steps", "label": label, "steps": steps, "integrity": integrity(since)}
    save(f"s05_load_steps-{label}", out)
    return out


@scenario
def s06_spike(label: str, restore: bool = True):
    """Pic brutal : 10 → 1000 utilisateurs en 5 s, maintenu 60 s, puis retour à 10."""
    if restore:
        restore_baseline()
    since = iso_now()
    sampler = Sampler(every=2).start()
    probe_t0 = now()
    result = k6(["-e", "MODE=spike", "-e", "SPIKE=1000"], f"{label}-spike", timeout=600)
    result["resources_timeline"] = sampler.stop()
    result["resources"] = _resource_peaks(result["resources_timeline"])
    after = [http("GET", API + "/health", timeout=5)[0] for _ in range(3)]
    out = {"scenario": "s06_spike", "label": label, "k6": result, "health_after": after,
           "integrity": integrity(since)}
    save(f"s06_spike-{label}", out)
    log(json.dumps({k: v for k, v in result.items() if k != "resources_timeline"}, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- S07 / S08 / S09 ressources


LIMITS = {"backend": "2", "postgres": "2", "redis": "1", "worker": "2"}


@scenario
def s07_cpu_starved(label: str, restore: bool = True):
    """CPU bridé à 0,15 cœur, tour à tour : web, PostgreSQL, Redis, worker (40 s chacun)."""
    out = {}
    for svc in ("backend", "postgres", "redis", "worker"):
        out[svc] = fault_run(
            f"s07_cpu_{svc}", label,
            inject=lambda svc=svc: docker("update", "--cpus", "0.15", container(svc)) and {"cpus": 0.15},
            heal=lambda svc=svc: docker("update", "--cpus", LIMITS[svc], container(svc)),
            during=40, after=20, users=15, restore=restore, probes=["renewal", "upload"],
        )
        restore = False
    return out


def big_pdf(mb: int, tag: str) -> bytes:
    """Scan volumineux incompressible, comme une numérisation JPEG (des zéros se compressaient
    à presque rien dans le ZIP et masquaient la consommation mémoire réelle)."""
    import os as _os
    return pdf_bytes(tag) + b"%" + _os.urandom(mb * 1024 * 1024) + b"\n%%EOF\n"


@scenario
def s08_memory(label: str, restore: bool = True):
    """Mémoire : 8 archives ZIP simultanées d'une AMM portant 12 scans de 20 Mo incompressibles
    (limite 1 Go)."""
    if restore:
        restore_baseline()
    since = iso_now()
    ceo = tokens(1, "CEO_ADMIN")[0]
    amm = ceo["amms"][7]
    for i in range(12):
        body, ctype = multipart({"kind": "AUTRE"}, {"file": (f"big{i}.pdf", big_pdf(20, f"big{i}"), "application/pdf")})
        http("POST", f"{API}/amms/{amm}/documents", ceo["token"], raw=body, content_type=ctype, timeout=120)
    sampler = Sampler(every=1).start()
    probe = Probe(users=5, think=0.5).start()
    time.sleep(5)
    before = restarts("backend")
    probe.mark("8 archives ZIP simultanées")
    r = burst(8, lambda i: http("GET", f"{API}/amms/{amm}/documents/archive.zip", ceo["token"], timeout=120)[0:2])
    time.sleep(20)
    probe.stop()
    rows = sampler.stop()
    state = docker("inspect", container("backend"), "--format", "{{.State.OOMKilled}} {{.RestartCount}}").split()
    mem = [row.get("backend_mem") for row in rows if row.get("backend_mem")]
    out = {
        "scenario": "s08_memory", "label": label,
        "archive_statuses": _count(x[0] for x in r),
        "archive_latency_s": sorted(round(x[1], 1) for x in r),
        "backend_restarts_during": restarts("backend") - before,
        "oom_killed_flag": state[0],
        "backend_mem_samples": mem[::3],
        "collateral": {"window": probe.window(5, 1e9), "outage": probe.outage(5)},
        "integrity": integrity(since),
    }
    save(f"s08_memory-{label}", out)
    log(json.dumps({k: v for k, v in out.items() if k != "backend_mem_samples"}, ensure_ascii=False))
    return out


def df(service: str, path: str) -> dict:
    line = docker("exec", container(service), "df", "-P", "-k", path).splitlines()[-1].split()
    return {"size_kb": int(line[1]), "used_kb": int(line[2]), "pct": int(line[4].rstrip("%"))}


MAX_FILL_FS_KB = 2 * 1024 * 1024  # 2 Go : au-delà, ce n'est pas le petit tmpfs du test


def fill_to(service: str, path: str, pct: int):
    """Ajoute un fichier de remplissage pour atteindre `pct` % d'occupation.

    Garde-fou : refuse tout système de fichiers de plus de 2 Go. Sans lui, une surcouche non
    appliquée a fait remplir le disque de la VM Docker (92,7 Go écrits puis supprimés, 18/09).
    """
    usage = df(service, path)
    if usage["size_kb"] > MAX_FILL_FS_KB:
        raise RuntimeError(f"{service}:{path} fait {usage['size_kb'] // 1024} Mo : pas le tmpfs de test, arrêt")
    target = usage["size_kb"] * pct // 100
    extra = target - usage["used_kb"]
    if extra > 0:
        n = len(docker("exec", container(service), "sh", "-c", f"ls {path}/filler-* 2>/dev/null | wc -l", check=False).split())
        docker("exec", container(service), "sh", "-c",
               f"dd if=/dev/zero of={path}/filler-{pct} bs=1024 count={extra} 2>/dev/null || true",
               check=False, timeout=120)
    return df(service, path)


@scenario
def s09_disk_full(label: str, restore: bool = True):
    """Disque de la base puis du stockage rempli à 80, 90, 95, 100 % ; détection ? dégâts ?"""
    from lab import COMPOSE, HERE
    disk = [*COMPOSE[:4], "-f", str(HERE / "docker-compose.disk.yml"), *COMPOSE[4:]]
    import subprocess
    Toxi.clear()
    compose("stop", "backend", "worker")
    subprocess.run([*disk, "up", "-d", "--no-deps", "--force-recreate", "--wait", "postgres", "minio"],
                   check=True, capture_output=True)
    # base neuve sur le tmpfs : on y charge l'état de référence ; bucket MinIO vide (recréé)
    subprocess.run([*COMPOSE, "exec", "-T", "postgres", "pg_restore", "-U", "amm", "-d", "amm", "--no-owner"],
                   stdin=open(HERE / "snapshots/baseline.dump", "rb"), capture_output=True, check=False)
    subprocess.run([*COMPOSE, "up", "--no-deps", "minio-init"], capture_output=True)
    for target, path in (("postgres", "/var/lib/postgresql/data"), ("minio", "/data")):
        if df(target, path)["size_kb"] > MAX_FILL_FS_KB:
            raise RuntimeError(f"surcouche disque non appliquée à {target} : arrêt du scénario")
    compose("up", "-d", "--no-deps", "backend", "worker")
    wait_healthy()
    since0 = iso_now()
    report = {"scenario": "s09_disk_full", "label": label, "levels": {}}
    try:
        for target in ("postgres", "minio"):
            path = "/var/lib/postgresql/data" if target == "postgres" else "/data"
            for pct in (80, 90, 95, 100):
                usage = fill_to(target, path, pct)
                since = iso_now()
                probe = Probe(users=8, think=0.4, write_ratio=0.3).start()
                ceo = tokens(1, "CEO_ADMIN")[0]
                up = upload_probe(ceo["token"], ceo["amms"][:20]).start(probe.t0)
                rn = renewal_probe(ceo["token"], ceo["amms"][20:40]).start(probe.t0)
                time.sleep(25)
                probe.stop(); up.stop(); rn.stop()
                health = http("GET", API + "/health", timeout=10)
                pg_state = docker("inspect", container("postgres"), "--format",
                                  "{{.State.Status}} restarts={{.RestartCount}}").strip()
                report["levels"][f"{target}_{pct}"] = {
                    "disk": usage, "window": probe.window(0, 1e9), "upload": up.summary(),
                    "upload_persistence": persisted_uploads(up) if target == "minio" or pct < 100 else "n/a",
                    "renewal": rn.summary(), "health": {"status": health[0], "body": health[2][:200].decode(errors="replace")},
                    "postgres": pg_state,
                }
                log(f"   {target} {pct}% : {report['levels'][f'{target}_{pct}']['window'].get('statuses')} "
                    f"upload {up.summary()['statuses']} renewal {rn.summary()['statuses']} health {health[0]} pg {pg_state}")
            # libération de l'espace : le service revient-il seul ?
            docker("exec", container(target), "sh", "-c", f"rm -f {path}/filler-*", check=False)
            time.sleep(10)
            report[f"{target}_after_cleanup"] = {
                "health": http("GET", API + "/health", timeout=10)[0],
                "pg": docker("inspect", container("postgres"), "--format", "{{.State.Status}} restarts={{.RestartCount}}").strip(),
            }
        # bucket recréé vide : les scans de référence n'y sont pas, on ne juge que la base
        report["integrity"] = integrity(since0, skip_storage=True)
    finally:
        compose("stop", "backend", "worker")
        subprocess.run([*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "--wait", "postgres", "minio"],
                       capture_output=True)
        restore_baseline()
    save(f"s09_disk_full-{label}", report)
    return report


# --------------------------------------------------------------------------- S16 redémarrage complet


@scenario
def s16_full_restart(label: str, restore: bool = True):
    """Toute la pile arrêtée puis relancée ; puis PostgreSQL absent 90 s au démarrage du web."""
    if restore:
        restore_baseline()
    since = iso_now()
    before = email_state("x")
    t0 = now()
    compose("down", timeout=180)
    t_down = now() - t0
    t1 = now()
    compose("up", "-d", timeout=300)
    ready = wait_healthy(timeout=300)
    worker_ready = wait_until(lambda: "pong" in compose("exec", "-T", "worker", "celery", "-A", "config",
                                                          "inspect", "ping", "--timeout", "3", check=False), 180, 2)
    part1 = {"stop_s": round(t_down, 1), "api_ready_s": round(now() - t1, 1), "worker_ready_after_api_s": worker_ready}
    # démarrage dans le désordre : la base arrive 90 s après le web et le worker
    ip = lambda: docker("inspect", container("backend"), "--format",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", check=False).strip()
    ip_before = ip()
    compose("stop", "postgres")
    compose("restart", "backend", "worker", timeout=180)
    time.sleep(90)
    web_state = docker("inspect", container("backend"), "--format", "{{.State.Status}} restarts={{.RestartCount}}").strip()
    t2 = now()
    compose("start", "postgres")
    direct_back = via_nginx_back = None
    while now() - t2 < 240 and via_nginx_back is None:
        if direct_back is None and http("GET", "http://localhost:19800/api/v1/health", timeout=3)[0] == 200:
            direct_back = round(now() - t2, 1)
        if http("GET", API + "/health", timeout=3)[0] == 200:
            via_nginx_back = round(now() - t2, 1)
        time.sleep(1)
    recovered = via_nginx_back
    ip_after = ip()
    stuck_diag = None
    if recovered is None:  # pourquoi l'API ne revient-elle pas ?
        stuck_diag = {
            "backend": docker("inspect", container("backend"), "--format",
                              "{{.State.Status}} restarts={{.RestartCount}} exit={{.State.ExitCode}} "
                              "health={{if .State.Health}}{{.State.Health.Status}}{{end}}", check=False).strip(),
            "backend_log": [l[:220] for l in docker("logs", "--tail", "25", container("backend"),
                                                     check=False).splitlines()][-25:],
        }
    worker_back = wait_until(lambda: "pong" in compose("exec", "-T", "worker", "celery", "-A", "config",
                                                         "inspect", "ping", "--timeout", "3", check=False), 180, 2)
    out = {"scenario": "s16_full_restart", "label": label, "cold_start": part1,
           "late_database": {"web_state_while_db_absent": web_state, "api_back_after_db_start_s": recovered,
                             "backend_direct_back_s": direct_back, "backend_ip_before": ip_before,
                             "backend_ip_after": ip_after, "worker_back_s": worker_back,
                             "stuck_diagnostic": stuck_diag},
           "integrity": integrity(since)}
    save(f"s16_full_restart-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- WebSocket


def k6_ws(clients: int, duration: int, tag: str, jitter: bool, during: Optional[Callable] = None) -> dict:
    from lab import HERE, RESULTS
    import subprocess
    (RESULTS / "tokens.json").write_text(json.dumps(tokens(200)))
    out_json = RESULTS / f"ws-{tag}.jsonl"
    if out_json.exists():
        out_json.unlink()
    cmd = ["docker", "run", "--rm", "--network", "amm-lab_lab", "-v", f"{HERE}:/data", "grafana/k6:1.3.0",
           "run", "--quiet", "--out", f"json=/data/results/ws-{tag}.jsonl",
           "--summary-export", f"/data/results/k6ws-{tag}.json",
           "-e", f"CLIENTS={clients}", "-e", f"DURATION={duration}", "-e", f"JITTER={'1' if jitter else '0'}",
           "/data/k6/websockets.js"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = now()
    extra = during(t0) if during else {}
    proc.wait(timeout=duration + 180)
    per_second: Dict[int, int] = {}
    counts = {"ws_attempts": 0, "ws_opened": 0, "ws_failed": 0, "ws_messages": 0}
    for line in out_json.read_text().splitlines():
        try:
            point = json.loads(line)
        except ValueError:
            continue
        if point.get("type") != "Point" or point["metric"] not in counts:
            continue
        counts[point["metric"]] += point["data"]["value"]
        if point["metric"] == "ws_attempts":
            sec = int(point["data"]["tags"].get("second", 0)) - int(t0)
            per_second[sec] = per_second.get(sec, 0) + 1
    return {"counts": counts, "attempts_per_second": dict(sorted(per_second.items())), **extra}


@scenario
def s17_ws_reconnect_herd(label: str, restore: bool = True, jitter: bool = False):
    """300 clients WebSocket connectés ; le web est tué : combien de reconnexions par seconde ?"""
    if restore:
        restore_baseline()

    def during(t0):
        time.sleep(40)
        sampler = Sampler(every=1).start()
        crash("backend", web_process())
        t_kill = round(now() - t0)
        time.sleep(60)
        return {"killed_at_s": t_kill, "resources": _resource_peaks(sampler.stop())}

    # le client k6 reproduit le frontend : jitter de reconnexion dans le code corrigé seulement
    jitter = jitter or label != "avant"
    out = k6_ws(300, 130, f"herd-{label}", jitter, during)
    kill = out["killed_at_s"]
    window = {s: n for s, n in out["attempts_per_second"].items() if kill - 2 <= s <= kill + 60}
    out.update({"scenario": "s17_ws_reconnect_herd", "label": label,
                "peak_attempts_per_second_after_kill": max(window.values(), default=0),
                "attempts_after_kill": sum(window.values())})
    save(f"s17_ws_reconnect_herd-{label}", out)
    log(json.dumps({k: v for k, v in out.items() if k != "attempts_per_second"}, ensure_ascii=False))
    log(f"   tentatives/s autour du crash : {window}")
    return out


@scenario
def s18_event_amplification(label: str, restore: bool = True):
    """100 clients connectés, 20 écritures d'AMM : combien d'événements reçus au total ?"""
    if restore:
        restore_baseline()

    def during(t0):
        time.sleep(25)
        ceo = tokens(1, "CEO_ADMIN")[0]
        for i in range(20):
            http("PATCH", f"{API}/amms/{ceo['amms'][i]}", ceo["token"], body={"notes": f"ampli {i}"})
            time.sleep(0.5)
        return {"writes": 20}

    out = k6_ws(100, 60, f"ampli-{label}", False, during)
    msgs = out["counts"]["ws_messages"] - out["counts"]["ws_opened"]  # moins le message « connected »
    out.update({"scenario": "s18_event_amplification", "label": label,
                "events_delivered": msgs, "events_per_write": round(msgs / 20, 1),
                "events_per_write_per_client": round(msgs / 20 / 100, 2)})
    save(f"s18_event_amplification-{label}", out)
    log(json.dumps({k: v for k, v in out.items() if k != "attempts_per_second"}, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- S04b réseau dégradé


@scenario
def s04b_network_unstable(label: str, restore: bool = True):
    """Réseau instable 60 s : PostgreSQL 150±120 ms découpé en petits paquets, 30 % des
    connexions Redis figées (perte), puis partition complète 30 s (DNS et TCP injoignables)."""
    def inject():
        Toxi.latency("postgres", 150, jitter=120)
        Toxi.slicer("postgres")
        Toxi.loss("redis", 0.3)
        return {"how": "pg jitter+slicer, redis 30% connexions figées"}

    unstable = fault_run("s04b_network_unstable", label, inject=inject, heal=lambda: Toxi.clear(),
                         restore=restore)

    def partition():
        docker("network", "disconnect", "amm-lab_lab", container("toxiproxy"))
        return {"how": "toxiproxy retiré du réseau : noms non résolus, connexions rompues"}

    def reconnect():
        docker("network", "connect", "--alias", "toxiproxy", "amm-lab_lab", container("toxiproxy"))

    partitioned = fault_run("s04c_network_partition", label, inject=partition, heal=reconnect,
                            during=30, after=60, restore=False)
    return {"unstable": unstable, "partition": partitioned}


@scenario
def s11d_worker_sigterm_long_task(label: str, restore: bool = True):
    """Arrêt propre du worker (docker stop : SIGTERM puis SIGKILL après 10 s) pendant des envois
    d'e-mails lents (15 s) : les e-mails partent-ils quand même ?"""
    if restore:
        restore_baseline()
    since = iso_now()
    mock_reset()
    mock_mode("slow", 15)
    enqueue_emails(4, "s11d")
    time.sleep(4)
    t0 = now()
    compose("stop", "worker", timeout=60)
    stop_s = round(now() - t0, 1)
    mock_mode("ok")
    compose("start", "worker")
    time.sleep(60)
    # avance rapide de 30 min, identique avant/après (last_attempt_at n'existe qu'après)
    psql("update notifications_notification set created_at=created_at - interval '30 minutes' "
         "where title like 'chaos s11d %'")
    try:
        psql("update notifications_notification set last_attempt_at=last_attempt_at - "
             "interval '30 minutes' where title like 'chaos s11d %'")
    except RuntimeError:
        pass
    sweep = exec_backend(
        "try:\n    from apps.core.tasks import recover_pending_work\n    print(recover_pending_work())\n"
        "except ImportError:\n    print('pas de rattrapage')", service="worker")
    time.sleep(30)
    out = {"scenario": "s11d_worker_sigterm_long_task", "label": label, "stop_took_s": stop_s,
           "emails": email_state("s11d"), "gmail_messages_received": mock_stats()["messages"],
           "sweeper": sweep.strip().splitlines()[-1][:200], "integrity": integrity(since)}
    save(f"s11d_worker_sigterm_long_task-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


@scenario
def s11e_redis_kill_with_queue(label: str, restore: bool = True):
    """200 tâches en file (worker arrêté), Redis tué (SIGKILL) puis relancé : combien restent ?"""
    if restore:
        restore_baseline()
    compose("stop", "worker")
    exec_backend(
        "from apps.documents.tasks import generate_document_preview as t\n"
        "for i in range(200): t.delay('00000000-0000-0000-0000-000000000000')")
    before = compose("exec", "-T", "redis", "redis-cli", "llen", "celery").strip()
    docker("kill", container("redis"))
    time.sleep(2)
    docker("start", container("redis"))
    time.sleep(5)
    after = compose("exec", "-T", "redis", "redis-cli", "llen", "celery").strip()
    compose("start", "worker")
    out = {"scenario": "s11e_redis_kill_with_queue", "label": label,
           "queued_before_kill": before, "queued_after_restart": after,
           "redis_persistence": "appendonly yes (docker-compose.prod.yml)"}
    save(f"s11e_redis_kill_with_queue-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


# --------------------------------------------------------------------------- Phase 3 : pannes combinées


@scenario
def p3a_load_redis_down_pg_slow(label: str, restore: bool = True):
    """Trafic important (40 utilisateurs) + Redis tué + PostgreSQL +150 ms, 60 s."""
    def inject():
        Toxi.latency("postgres", 150)
        docker("kill", container("redis"))
        return {"how": "redis kill + pg latency 150ms", "users": 40}

    def heal():
        docker("start", container("redis"))
        Toxi.clear("postgres")

    return fault_run("p3a_load_redis_down_pg_slow", label, inject=inject, heal=heal, users=40,
                     restore=restore)


@scenario
def p3b_crash_worker_down_gmail_down(label: str, restore: bool = True):
    """Web tué + worker arrêté + API Gmail en panne ; alertes et e-mails produits pendant ce temps."""
    if restore:
        restore_baseline()
    since = iso_now()
    mock_reset()
    ceo = tokens(1, "CEO_ADMIN")[0]
    probe = Probe(users=10, think=0.5).start()
    time.sleep(10)
    probe.mark("worker arrêté, Gmail en panne, web tué")
    compose("stop", "worker")
    mock_mode("http500")
    crash("backend", web_process())
    time.sleep(3)
    ids = enqueue_emails(10, "p3b")
    docs = upload_docs(ceo["token"], ceo["amms"], 5, "p3b")
    time.sleep(40)
    probe.mark("worker relancé (Gmail toujours en panne 60 s)")
    compose("start", "worker")
    time.sleep(60)
    probe.mark("Gmail rétabli")
    mock_mode("ok")
    time.sleep(90)
    probe.stop()
    out = {"scenario": "p3b_crash_worker_down_gmail_down", "label": label,
           "api": {"window": probe.window(0, 1e9), "outage": probe.outage(10)},
           "emails": email_state("p3b"), "gmail_messages_received": mock_stats()["messages"],
           "previews": f"{previews_done(docs)}/{len(docs)}", "integrity": integrity(since)}
    save(f"p3b_crash_worker_down_gmail_down-{label}", out)
    log(json.dumps(out, ensure_ascii=False))
    return out


@scenario
def p3c_cpu_dblatency_spike(label: str, restore: bool = True):
    """Web bridé à 0,5 cœur + PostgreSQL +50 ms + pic brutal 10 → 500 utilisateurs."""
    if restore:
        restore_baseline()
    since = iso_now()
    docker("update", "--cpus", "0.5", container("backend"))
    Toxi.latency("postgres", 50)
    try:
        sampler = Sampler(every=2).start()
        result = k6(["-e", "MODE=spike", "-e", "SPIKE=500"], f"{label}-p3c", timeout=600)
        result["resources"] = _resource_peaks(sampler.stop())
    finally:
        docker("update", "--cpus", LIMITS["backend"], container("backend"))
        Toxi.clear("postgres")
    time.sleep(5)
    after = [http("GET", API + "/health", timeout=5)[0] for _ in range(3)]
    out = {"scenario": "p3c_cpu_dblatency_spike", "label": label, "k6": result, "health_after": after,
           "integrity": integrity(since)}
    save(f"p3c_cpu_dblatency_spike-{label}", out)
    log(json.dumps(out, ensure_ascii=False)[:1500])
    return out


# --------------------------------------------------------------------------- Phase 4 : observabilité


@scenario
def s19_observability(label: str, restore: bool = True):
    """Redis coupé 30 s sous trafic : les journaux et métriques répondent-ils aux questions
    QUOI, QUAND, POURQUOI, QUEL composant, COMBIEN d'utilisateurs, COMBIEN de temps, reprise ?"""
    if restore:
        restore_baseline()
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    probe = Probe(users=10, think=0.4).start()
    time.sleep(10)
    probe.mark("Redis coupé")
    docker("kill", container("redis"))
    time.sleep(30)
    probe.mark("Redis rétabli")
    docker("start", container("redis"))
    time.sleep(40)
    probe.stop()
    logs = docker("logs", "--since", started, container("backend"), check=False).splitlines()
    events, access = [], []
    for line in logs:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("logger") == "amm.access":
            access.append(rec)
        elif rec.get("level") in ("WARNING", "ERROR") and any(
                word in rec.get("msg", "") for word in ("disjoncteur", "indisponible", "rétablie")):
            events.append({k: rec.get(k) for k in ("ts", "level", "logger", "msg", "request_id")})
    failed = [a for a in access if a.get("status", 0) >= 500]
    metrics = http("GET", "http://localhost:19800/metrics", timeout=5)[2].decode(errors="replace")
    degraded = [l for l in metrics.splitlines() if l.startswith("amm_degraded_operations_total")]
    out = {
        "scenario": "s19_observability", "label": label,
        "json_log_lines": len(access), "requests_5xx_in_logs": len(failed),
        "users_with_5xx": len({a.get("user_id") for a in failed}),
        "breaker_events": events[:6], "degraded_counters": degraded,
        "sample_access_line": access[len(access) // 2] if access else None,
        "probe_outage": probe.outage(10), "probe_window": probe.window(10, 1e9),
    }
    save(f"s19_observability-{label}", out)
    log(json.dumps(out, ensure_ascii=False, indent=1)[:3000])
    return out


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?")
    parser.add_argument("--label", default="avant")
    parser.add_argument("--no-restore", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    import os

    from lab import HERE
    os.environ["AMM_BACKEND_SRC"] = str(
        HERE / "frozen-avant-backend" if args.label == "avant" else HERE.parent / "backend"
    )
    os.environ["AMM_BACKEND_IMAGE"] = "amm-lab-backend:latest" if args.label == "avant" else "amm-lab-backend:apres"
    # « apres2 » : code corrigé et 2 processus web (mesure de capacité)
    os.environ["AMM_WEB_CONCURRENCY"] = "2" if args.label == "apres2" else "1"
    os.environ["AMM_NGINX_CONF"] = str(
        HERE / "frozen-avant-nginx.conf" if args.label == "avant" else HERE.parent / "docker/nginx.conf"
    )
    if args.list or not args.name:
        for name, fn in SCENARIOS.items():
            print(f"{name:32} {fn.__doc__.strip().splitlines()[0]}")
        return
    try:
        SCENARIOS[args.name](args.label, restore=not args.no_restore)
    finally:
        Toxi.clear()
        mock_reset()


if __name__ == "__main__":
    main()
