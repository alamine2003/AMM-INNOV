"""Boîte à outils de la campagne de chaos (Python 3.9+, bibliothèque standard uniquement).

Tout ce qui est destructif vise EXCLUSIVEMENT le projet Compose `amm-lab` (données jetables,
restaurables par `restore_baseline()`). Aucune fonction ne sait joindre un autre environnement.

Briques :
- `compose(...)`, `exec_backend(...)` : pilotage du labo ;
- `Toxi` : latence, coupure, perte, connexions figées via l'API toxiproxy ;
- `Probe` : trafic « utilisateurs » continu pendant une panne, chaque requête horodatée,
  pour répondre à QUAND / COMBIEN d'utilisateurs / COMBIEN de temps / récupération ;
- `integrity(since)` : invariants métier (manage.py check_integrity --json) après chaque test.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-f", str(HERE / "docker-compose.lab.yml"), "-p", "amm-lab"]
API = os.environ.get("LAB_API", "http://localhost:19080/api/v1")
TOXI = os.environ.get("LAB_TOXI", "http://localhost:19474")
MOCK = os.environ.get("LAB_MOCK", "http://localhost:19081")
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)


def now() -> float:
    return time.time()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- docker


def compose(*args: str, check: bool = True, timeout: int = 300) -> str:
    result = subprocess.run(
        [*COMPOSE, *args], capture_output=True, text=True, timeout=timeout
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"compose {' '.join(args)} : {result.stderr[-2000:]}")
    return result.stdout + result.stderr


def exec_backend(code: str, service: str = "backend", timeout: int = 300) -> str:
    """Exécute du Python dans le conteneur (Django initialisé)."""
    script = (
        "import os,sys,django;sys.path.insert(0,'/app');"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.prod');django.setup()\n"
        + code
    )
    return compose("exec", "-T", service, "python", "-c", script, timeout=timeout)


_password: Optional[str] = None


def lab_password() -> str:
    """Mot de passe des comptes du laboratoire, lu dans seed_demo plutôt que recopié ici."""
    global _password
    if _password is None:
        _password = exec_backend(
            "from apps.accounts.management.commands.seed_demo import PASSWORD; print(PASSWORD)"
        ).strip().splitlines()[-1]
    return _password


def psql(sql: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "amm", "-d", "amm", "-At", "-c", sql)


def container(service: str) -> str:
    return f"amm-lab-{service}-1"


def docker(*args: str, check: bool = True, timeout: int = 120) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} : {result.stderr[-2000:]}")
    return result.stdout + result.stderr


def wait_healthy(url: str = API + "/health", timeout: float = 180, expect: int = 200) -> float:
    """Attend que `url` réponde `expect` ; renvoie le temps écoulé (s)."""
    started = now()
    while now() - started < timeout:
        code, _, _ = http("GET", url, timeout=3)
        if code == expect:
            return now() - started
        time.sleep(0.5)
    raise TimeoutError(f"{url} pas {expect} après {timeout}s")


# --------------------------------------------------------------------------- HTTP


def http(method: str, url: str, token: str = None, body=None, timeout: float = 30,
         headers: dict = None, raw: bytes = None, content_type: str = None):
    """(status, secondes, corps) ; status 0 = pas de réponse (timeout, connexion refusée)."""
    data = raw
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if content_type:
        hdrs["Content-Type"] = content_type
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    started = now()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, now() - started, payload
    except urllib.error.HTTPError as exc:
        return exc.code, now() - started, exc.read()
    except Exception as exc:  # timeout, refus, reset
        return 0, now() - started, str(exc).encode()


def multipart(fields: dict, files: dict):
    boundary = f"----lab{random.randint(0, 1 << 60):x}"
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    items = []
    for name, spec in files.items():
        for filename, content, ctype in (spec if isinstance(spec, list) else [spec]):
            items.append((name, filename, content, ctype))
    for name, filename, content, ctype in items:
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n"
            ).encode()
            + content
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def pdf_bytes(tag: str) -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        + f"% chaos {tag} {random.random()}\n".encode()
    )


# --------------------------------------------------------------------------- données


def tokens(n: int = 20, role: str = None) -> List[dict]:
    """Jetons d'accès émis directement (utilisateurs « déjà connectés », sans throttle login)."""
    filt = f"role='{role}'" if role else ""
    out = exec_backend(
        "import json\n"
        "from apps.accounts.models import User\n"
        "from rest_framework_simplejwt.tokens import AccessToken\n"
        f"qs=User.objects.filter(is_active=True{', ' + filt if filt else ''}).order_by('email')[:{n}]\n"
        "from apps.amm.models import MarketingAuthorization as M\n"
        "def scope(u):\n"
        "    q=M.objects.all() if u.is_global else M.objects.filter(country__in=u.countries.all())\n"
        "    return [str(x) for x in q.order_by('id').values_list('id',flat=True)[:60]]\n"
        "print(json.dumps([{'email':u.email,'role':u.role,'token':str(AccessToken.for_user(u)),'amms':scope(u)} for u in qs]))"
    )
    return json.loads(out.strip().splitlines()[-1])


def ceo_token() -> str:
    return tokens(1, "CEO_ADMIN")[0]["token"]


def amm_ids(n: int = 200) -> List[str]:
    out = psql(f"select id from amm_marketingauthorization order by id limit {n}")
    return [line for line in out.split() if len(line) == 36]


# --------------------------------------------------------------------------- toxiproxy


class Toxi:
    """Pannes réseau réversibles entre le backend et ses dépendances."""

    @staticmethod
    def _call(method: str, path: str, body=None):
        # retirer un toxique attend que ses données retenues s'écoulent (slicer, latence) : 30 s
        for attempt in range(3):
            code, _, payload = http(method, TOXI + path, body=body, timeout=30)
            if 0 < code < 300:
                return json.loads(payload or b"{}") if payload else {}
            if code == 404 and method == "DELETE":
                return {}
            time.sleep(2)
        raise RuntimeError(f"toxiproxy {method} {path} -> {code} {payload[:200]}")

    @classmethod
    def latency(cls, proxy: str, ms: int, jitter: int = 0, stream: str = "downstream"):
        return cls._call("POST", f"/proxies/{proxy}/toxics", {
            "name": f"latency_{stream}", "type": "latency", "stream": stream,
            "attributes": {"latency": ms, "jitter": jitter},
        })

    @classmethod
    def timeout(cls, proxy: str, ms: int = 0):
        """Données retenues : la connexion reste ouverte sans réponse (dépendance figée)."""
        return cls._call("POST", f"/proxies/{proxy}/toxics", {
            "name": "timeout", "type": "timeout", "stream": "downstream",
            "attributes": {"timeout": ms},
        })

    @classmethod
    def reset_peer(cls, proxy: str, ms: int = 0):
        return cls._call("POST", f"/proxies/{proxy}/toxics", {
            "name": "reset", "type": "reset_peer", "stream": "downstream",
            "attributes": {"timeout": ms},
        })

    @classmethod
    def loss(cls, proxy: str, toxicity: float):
        """Perte : une fraction des connexions voit ses données retenues (≈ paquets perdus)."""
        return cls._call("POST", f"/proxies/{proxy}/toxics", {
            "name": "loss", "type": "timeout", "stream": "downstream", "toxicity": toxicity,
            "attributes": {"timeout": 0},
        })

    @classmethod
    def slicer(cls, proxy: str):
        """Réseau instable : paquets découpés et retardés aléatoirement."""
        return cls._call("POST", f"/proxies/{proxy}/toxics", {
            "name": "slicer", "type": "slicer", "stream": "downstream",
            "attributes": {"average_size": 64, "size_variation": 48, "delay": 20000},
        })

    @classmethod
    def disable(cls, proxy: str):
        return cls._call("POST", f"/proxies/{proxy}", {"enabled": False})

    @classmethod
    def enable(cls, proxy: str):
        return cls._call("POST", f"/proxies/{proxy}", {"enabled": True})

    @classmethod
    def clear(cls, proxy: Optional[str] = None):
        proxies = [proxy] if proxy else ["postgres", "redis", "minio", "gmail"]
        for name in proxies:
            cls.enable(name)
            for toxic in cls._call("GET", f"/proxies/{name}/toxics"):
                cls._call("DELETE", f"/proxies/{name}/toxics/{toxic['name']}")


def mock_mode(mode: str, delay: float = 30.0):
    return http("POST", MOCK + "/_mode", body={"mode": mode, "delay": delay}, timeout=5)


def mock_stats() -> dict:
    return json.loads(http("GET", MOCK + "/_stats", timeout=5)[2])


def mock_reset():
    return http("POST", MOCK + "/_reset", body={}, timeout=5)


# --------------------------------------------------------------------------- sonde


@dataclass
class Sample:
    t: float
    user: int
    kind: str
    status: int
    latency: float


@dataclass
class Probe:
    """`users` utilisateurs simulés, chacun enchaînant lectures et écritures avec pause."""

    users: int = 10
    think: float = 0.5
    write_ratio: float = 0.15
    timeout: float = 30
    samples: List[Sample] = field(default_factory=list)
    events: List[tuple] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _threads: List[threading.Thread] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self):
        self.creds = tokens(max(self.users, 1))
        self.amms = amm_ids(300)
        self.t0 = now()
        for i in range(self.users):
            thread = threading.Thread(target=self._run, args=(i,), daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def mark(self, label: str):
        self.events.append((now() - self.t0, label))
        log(f"  ⟶ {label}")

    def _request(self, user: int):
        cred = self.creds[user % len(self.creds)]
        token = cred["token"]
        roll = random.random()
        amm = random.choice(cred["amms"] or self.amms)
        if roll < self.write_ratio:
            return "write", http("PATCH", f"{API}/amms/{amm}", token,
                                 body={"notes": f"sonde {now():.3f}"}, timeout=self.timeout)
        if roll < self.write_ratio + 0.35:
            return "list", http("GET", f"{API}/amms?page={random.randint(1, 5)}", token,
                                timeout=self.timeout)
        if roll < self.write_ratio + 0.55:
            return "detail", http("GET", f"{API}/amms/{amm}", token, timeout=self.timeout)
        if roll < self.write_ratio + 0.70:
            return "analytics", http("GET", f"{API}/analytics/africa", token, timeout=self.timeout)
        if roll < self.write_ratio + 0.80:
            return "alerts", http("GET", f"{API}/alerts?status=OPEN", token, timeout=self.timeout)
        return "me", http("GET", f"{API}/me", token, timeout=self.timeout)

    def _run(self, user: int):
        while not self._stop.is_set():
            kind, (status, latency, _) = self._request(user)
            with self._lock:
                self.samples.append(Sample(now() - self.t0, user, kind, status, latency))
            self._stop.wait(self.think * random.uniform(0.5, 1.5))

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=self.timeout + 5)
        return self

    # --- analyse

    @staticmethod
    def ok(sample: Sample) -> bool:
        # 4xx métier (404 hors périmètre…) = réponse correcte ; 0/5xx = échec vu par l'utilisateur
        return 0 < sample.status < 500

    def window(self, start: float, end: float, kind: Optional[str] = None) -> dict:
        rows = [s for s in self.samples if start <= s.t < end and (kind is None or s.kind == kind)]
        if not rows:
            return {"requests": 0}
        lat = sorted(s.latency for s in rows)
        failed = [s for s in rows if not self.ok(s)]
        return {
            "requests": len(rows),
            "errors": len(failed),
            "error_rate": round(len(failed) / len(rows), 3),
            "users_affected": len({s.user for s in failed}),
            "p50_ms": round(pct(lat, 50) * 1000),
            "p95_ms": round(pct(lat, 95) * 1000),
            "p99_ms": round(pct(lat, 99) * 1000),
            "max_ms": round(lat[-1] * 1000),
            "statuses": dict(sorted(count_by(rows, lambda s: s.status).items())),
        }

    def outage(self, after: float = 0.0) -> dict:
        """Première et dernière erreur après `after`, et retour au nominal."""
        failed = [s for s in self.samples if s.t >= after and not self.ok(s)]
        if not failed:
            return {"first_error_s": None, "last_error_s": None, "duration_s": 0}
        first, last = failed[0].t, max(s.t + s.latency for s in failed)
        return {
            "first_error_s": round(first, 1),
            "last_error_s": round(last, 1),
            "duration_s": round(last - first, 1),
            "failed_requests": len(failed),
            "users_affected": len({s.user for s in failed}),
        }

    def timeline(self, bucket: float = 5.0) -> List[dict]:
        if not self.samples:
            return []
        end = max(s.t for s in self.samples)
        out, t = [], 0.0
        while t <= end:
            w = self.window(t, t + bucket)
            if w.get("requests"):
                out.append({"t": t, **{k: w[k] for k in ("requests", "errors", "p50_ms", "p95_ms", "max_ms")}})
            t += bucket
        return out


def pct(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def count_by(rows, key: Callable) -> Dict:
    out: Dict = {}
    for row in rows:
        out[key(row)] = out.get(key(row), 0) + 1
    return out


# --------------------------------------------------------------------------- mesures


def integrity(since: Optional[str] = None, skip_storage: bool = False) -> dict:
    args = ["exec", "-T", "backend", "python", "manage.py", "check_integrity", "--json"]
    if since:
        args += ["--since", since]
    if skip_storage:
        args.append("--skip-storage")
    out = compose(*args, check=False, timeout=600)
    line = [x for x in out.splitlines() if x.startswith("{")]
    if not line:
        return {"ok": None, "error": out[-1500:]}
    report = json.loads(line[-1])
    return {
        "ok": report["ok"],
        "violations": report["violations"],
        "samples": {c["code"]: c["sample"][:3] for c in report["checks"] if c["count"]},
    }


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def pg_connections() -> dict:
    out = psql(
        "select coalesce(state,'?'), count(*) from pg_stat_activity "
        "where datname='amm' group by 1"
    )
    return {line.split("|")[0]: int(line.split("|")[1]) for line in out.split() if "|" in line}


def redis_info() -> dict:
    out = compose("exec", "-T", "redis", "redis-cli", "info")
    keep = ("connected_clients", "used_memory_human", "instantaneous_ops_per_sec", "blocked_clients")
    info = {}
    for line in out.splitlines():
        if ":" in line and line.split(":")[0] in keep:
            info[line.split(":")[0]] = line.split(":")[1].strip()
    info["celery_queue"] = compose("exec", "-T", "redis", "redis-cli", "llen", "celery").strip()
    return info


class Sampler:
    """CPU / RAM des conteneurs du labo, connexions PostgreSQL, clients Redis, toutes les `every` s."""

    def __init__(self, every: float = 2.0):
        self.every, self.rows, self._stop = every, [], threading.Event()

    def start(self):
        self.t0 = now()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            row = {"t": round(now() - self.t0, 1)}
            try:
                out = docker("stats", "--no-stream", "--format",
                             "{{.Name}};{{.CPUPerc}};{{.MemUsage}}", timeout=20)
                others = 0.0
                for line in out.splitlines():
                    name, cpu, mem = line.split(";")
                    if not name.startswith("amm-lab-"):
                        others += float(cpu.rstrip("%") or 0)  # bruit d'autres piles Docker
                    if name.startswith("amm-lab-"):
                        svc = name[len("amm-lab-"):-2]
                        row[f"{svc}_cpu"] = float(cpu.rstrip("%") or 0)
                        row[f"{svc}_mem"] = mem.split("/")[0].strip()
                row["others_cpu"] = round(others, 1)
                row["pg"] = pg_connections()
            except Exception as exc:  # une mesure ratée ne doit pas arrêter le test
                row["error"] = str(exc)[:200]
            self.rows.append(row)
            self._stop.wait(self.every)

    def stop(self):
        self._stop.set()
        self.thread.join(timeout=30)
        return self.rows


def save(name: str, data) -> Path:
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    log(f"résultats → {path.relative_to(HERE.parent)}")
    return path


# --------------------------------------------------------------------------- remise à zéro


def restore_baseline():
    """Remet le labo dans l'état de référence (base, scans, Redis vide, réseau sain)."""
    log("restauration de l'état de référence")
    Toxi.clear()
    mock_reset()
    compose("stop", "backend", "worker")
    compose("exec", "-T", "postgres", "psql", "-U", "amm", "-d", "postgres", "-c",
            "select pg_terminate_backend(pid) from pg_stat_activity where datname='amm' and pid<>pg_backend_pid()")
    compose("exec", "-T", "postgres", "dropdb", "-U", "amm", "--if-exists", "amm")
    compose("exec", "-T", "postgres", "createdb", "-U", "amm", "amm")
    subprocess.run(
        [*COMPOSE, "exec", "-T", "postgres", "pg_restore", "-U", "amm", "-d", "amm", "--no-owner"],
        stdin=open(HERE / "snapshots/baseline.dump", "rb"), capture_output=True, check=False,
    )
    # statistiques SQL (scénario 14) : l'extension vit dans la base, recréée à chaque restauration
    psql("create extension if not exists pg_stat_statements")
    compose("stop", "minio")
    docker("run", "--rm", "-v", "amm-lab_miniodata:/data", "-v", f"{HERE / 'snapshots'}:/snap:ro",
           "python:3.12-slim", "sh", "-c",
           "rm -rf /data/* /data/.minio.sys && tar xzf /snap/minio-baseline.tgz -C /data")
    compose("up", "-d", "--no-deps", "--wait", "minio")
    compose("exec", "-T", "redis", "redis-cli", "flushall")
    # --no-deps : ne pas « reconverger » les dépendances vers le seul fichier de base (cela avait
    # défait la surcouche disque du scénario s09)
    compose("up", "-d", "--no-deps", "backend", "worker")
    wait_healthy("http://localhost:19800/api/v1/health")  # backend en direct
    try:
        wait_healthy(timeout=15)  # puis à travers nginx
    except TimeoutError:
        # nginx d'origine garde l'IP du backend résolue à son démarrage (constat s16) : réparation
        # de mise en place uniquement, jamais pendant une injection de panne.
        log("nginx vise une IP périmée du backend : redémarrage de nginx (mise en place)")
        compose("up", "-d", "--force-recreate", "nginx")
        wait_healthy()
    log("état de référence restauré")


def app_pids(service: str, needle: str) -> List[int]:
    """PID des processus dont la ligne de commande contient `needle` (hors PID 1 = init)."""
    out = docker("exec", container(service), "python", "-c",
                 "import os\n"
                 "for p in os.listdir('/proc'):\n"
                 "  if p.isdigit() and p!='1':\n"
                 "    try: c=open(f'/proc/{p}/cmdline','rb').read().replace(b'\\0',b' ')\n"
                 "    except Exception: continue\n"
                 f"    if {needle!r}.encode() in c and b'python -c' not in c: print(p)")
    return [int(x) for x in out.split() if x.isdigit()]


def crash(service: str, needle: str, signal: str = "KILL") -> List[int]:
    """Tue le processus applicatif de l'intérieur : sortie inattendue ⇒ politique de redémarrage."""
    pids = app_pids(service, needle)
    if pids:
        # pas de /bin/kill dans l'image slim : signal envoyé par Python
        docker("exec", container(service), "python", "-c",
               f"import os,signal\nfor p in {pids!r}: os.kill(p, signal.SIG{signal})")
    return pids


def restarts(service: str) -> int:
    return int(docker("inspect", container(service), "--format", "{{.RestartCount}}").strip())
