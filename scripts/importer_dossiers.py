#!/usr/bin/env python3
"""Importe des dossiers AMM dans AMM GH depuis le Terminal, pays par pays, sans navigateur.

Même envoi que la page « Import de dossiers AMM » : un import par dossier de présentation,
les décisions groupées au-dessus des produits jointes à chacun (« Documents communs »), les
fichiers déjà présents sur le serveur non renvoyés (empreinte SHA-256).

Usage (le mot de passe est demandé, jamais affiché ni enregistré) :

    python3 importer_dossiers.py "…/PRÊT À IMPORTER"                 # tout, du plus petit pays au plus gros
    python3 importer_dossiers.py "…/PRÊT À IMPORTER/CARDIO AFRIQUE/GABON"   # un seul pays
    python3 importer_dossiers.py --liste "…/PRÊT À IMPORTER"          # montre le plan sans rien envoyer

Reprise : les produits déjà envoyés sont notés dans « .import-amm-gh.json » (dossier courant) ;
relancer la même commande reprend là où elle s'était arrêtée.

Aucune dépendance : Python 3 fourni avec macOS suffit.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://amm-innov-api.onrender.com/api/v1"
FILE_MAX = 25 * 1024**2
FOLDER_MAX = 250 * 1024**2
FILES_MAX = 200
FORMATS = re.compile(r"\.(pdf|jpe?g|png)$", re.I)
PERIOD = re.compile(r"^(amm[\s_-]*)?(origine|original|initial|renouv|renouvellement|renewal)", re.I)
IGNORED = {".DS_Store", "Thumbs.db"}
STATE = ".import-amm-gh.json"
GAMMES = ("GAMME GENERALE AFRIQUE", "CARDIO AFRIQUE", "BIEN ETRE AFRIQUE")


# --- Lecture des dossiers ------------------------------------------------------------------


def folder_files(folder: str) -> tuple[list[dict], list[str]]:
    """Fichiers du dossier, chemins relatifs à son parent (« SENEGAL/ALFA-GH/…/x.pdf »)."""
    parent = os.path.dirname(os.path.abspath(folder))
    kept, ignored = [], []
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            if name in IGNORED or name.startswith("~$") or name.startswith("._"):
                continue
            full = os.path.join(root, name)
            path = os.path.relpath(full, parent).replace(os.sep, "/")
            size = os.path.getsize(full)
            if not FORMATS.search(name):
                ignored.append(f"{path} (format non lu)")
            elif not size:
                ignored.append(f"{path} (fichier vide)")
            elif size > FILE_MAX:
                ignored.append(f"{path} (plus de 25 Mo)")
            else:
                kept.append({"full": full, "path": path, "size": size})
    return kept, ignored


def split_by_product(files: list[dict]) -> list[dict]:
    """Un import par dossier de présentation (copie de `splitByProduct` du site)."""
    if not files:
        return []
    root = files[0]["path"].split("/")[0]

    def product_dirs(parts):
        dirs = parts[1:-1]
        while dirs and PERIOD.search(dirs[-1]):
            dirs = dirs[:-1]
        return dirs

    entries = [
        {"file": f, "parts": f["path"].split("/"), "dirs": product_dirs(f["path"].split("/"))}
        for f in files
    ]
    keys = {"/".join(e["dirs"]) for e in entries}

    def is_parent(key):
        return any(o != key and (key == "" or o.startswith(key + "/")) for o in keys)

    groups: dict[str, dict] = {}
    common = []
    for e in entries:
        key = "/".join(e["dirs"])
        if not key or is_parent(key):
            common.append(e)
            continue
        groups.setdefault(key, {"dirs": e["dirs"], "files": []})["files"].append(e["file"])
    if len(groups) < 2:
        return [{"name": root, "files": files}]
    result = []
    for key, group in groups.items():
        name = " - ".join([root, *group["dirs"]])[:255].rstrip()
        seen, items = set(), []

        def add(f, path):
            if path not in seen:
                seen.add(path)
                items.append({**f, "path": path})

        for f in group["files"]:
            parts = f["path"].split("/")
            add(f, "/".join([name, *parts[1 + len(group["dirs"]) :]]))
        for e in common:
            prefix = "/".join(e["dirs"])
            if prefix and not key.startswith(prefix + "/"):
                continue
            add(e["file"], "/".join([name, "Documents communs", e["parts"][-1]]))
        result.append({"name": name, "files": items})
    return result


def country_folders(target: str) -> list[str]:
    """Le dossier donné, ou (dossier « PRÊT À IMPORTER ») chaque gamme/pays, du plus léger au plus lourd."""
    subdirs = [d for d in sorted(os.listdir(target)) if os.path.isdir(os.path.join(target, d))]
    if not any(d in GAMMES for d in subdirs):
        return [target]
    found = []
    for gamme in subdirs:
        for pays in sorted(os.listdir(os.path.join(target, gamme))):
            path = os.path.join(target, gamme, pays)
            if os.path.isdir(path):
                count = sum(len([n for n in names if FORMATS.search(n)]) for _, _, names in os.walk(path))
                found.append((count, path))
    return [path for _, path in sorted(found)]


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# --- API -----------------------------------------------------------------------------------


class Client:
    def __init__(self, api: str):
        self.api = api.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.access = None

    def _send(self, method, path, body=None, content_type="application/json", timeout=300):
        request = urllib.request.Request(self.api + path, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", content_type)
        if self.access:
            request.add_header("Authorization", f"Bearer {self.access}")
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def login(self, email: str, password: str) -> None:
        self.access = None
        data = self._send("POST", "/auth/login", json.dumps({"email": email, "password": password}).encode())
        self.access = data["access"]

    def refresh(self) -> None:
        self.access = None
        self.access = self._send("POST", "/auth/refresh", b"{}")["access"]

    def call(self, method, path, body=None, content_type="application/json", timeout=300):
        """Appel avec reconnexion (jeton expiré) et patience (service Render qui redémarre)."""
        for attempt in range(8):
            try:
                return self._send(method, path, body, content_type, timeout)
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt < 7:
                    self.refresh()
                    continue
                if exc.code in (502, 503, 504) and attempt < 7:
                    wait(attempt, f"serveur indisponible ({exc.code})")
                    continue
                detail = exc.read().decode(errors="replace")[:500]
                raise RuntimeError(f"{exc.code} : {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt < 7:
                    wait(attempt, f"connexion perdue ({exc})")
                    continue
                raise
        raise RuntimeError("serveur injoignable")


def wait(attempt: int, why: str) -> None:
    seconds = min(30 * (attempt + 1), 180)
    print(f"      … {why}, nouvel essai dans {seconds} s")
    time.sleep(seconds)


def multipart(fields: dict, files: list[dict]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for f in files:
        filename = os.path.basename(f["path"]).replace('"', "'")
        kind = "application/pdf" if f["path"].lower().endswith(".pdf") else "image/jpeg"
        if f["path"].lower().endswith(".png"):
            kind = "image/png"
        chunks.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
                f'filename="{filename}"\r\nContent-Type: {kind}\r\n\r\n'
            ).encode()
        )
        with open(f["full"], "rb") as handle:
            chunks.append(handle.read())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def upload(client: Client, group: dict) -> dict:
    files = group["files"]
    digests = {f["path"]: sha256(f["full"]) for f in files}
    known: set[str] = set()
    unique = sorted(set(digests.values()))
    for start in range(0, len(unique), 1000):
        answer = client.call(
            "POST", "/dossier-imports/known-files", json.dumps({"sha256": unique[start : start + 1000]}).encode()
        )
        known.update(answer.get("known", []))
    sent = [f for f in files if digests[f["path"]] not in known]
    reused = [{"path": f["path"], "sha256": digests[f["path"]]} for f in files if digests[f["path"]] in known]
    body, content_type = multipart(
        {
            "paths": json.dumps([f["path"] for f in sent], ensure_ascii=False),
            "reused": json.dumps(reused, ensure_ascii=False),
            "root_name": group["name"],
        },
        sent,
    )
    batch = client.call("POST", "/dossier-imports", body, content_type, timeout=600)
    return {"id": batch.get("id"), "sent": len(sent), "reused": len(reused)}


# --- Programme -----------------------------------------------------------------------------


def load_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"done": {}}


def save_state(state: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import de dossiers AMM dans AMM GH, pays par pays.")
    parser.add_argument("dossiers", nargs="+", help="« PRÊT À IMPORTER », une gamme ou un pays")
    parser.add_argument("--email", help="adresse de connexion à AMM GH")
    parser.add_argument("--api", default=API)
    parser.add_argument("--liste", action="store_true", help="afficher le plan sans rien envoyer")
    parser.add_argument("--pause", type=float, default=2.0, help="secondes entre deux produits")
    args = parser.parse_args()

    plan = []
    for target in args.dossiers:
        if not os.path.isdir(target):
            print(f"Dossier introuvable : {target}")
            return 1
        plan.extend(country_folders(target))

    state = load_state()
    client = None
    if not args.liste:
        email = args.email or input("E-mail AMM GH : ").strip()
        client = Client(args.api)
        try:
            client.login(email, getpass.getpass("Mot de passe (non affiché) : "))
        except Exception as exc:  # noqa: BLE001 - message clair pour l'utilisateur
            print(f"Connexion refusée : {exc}")
            return 1
        print("Connecté.\n")

    totals = {"produits": 0, "fichiers": 0, "deja": 0, "erreurs": 0}
    for number, folder in enumerate(plan, start=1):
        files, ignored = folder_files(folder)
        groups = split_by_product(files)
        label = os.path.relpath(folder, os.path.dirname(os.path.dirname(folder)))
        print(f"[{number}/{len(plan)}] {label} : {len(files)} fichiers, {len(groups)} produit(s)")
        for line in ignored:
            print(f"      mis de côté : {line}")
        for group in groups:
            key = f"{folder}::{group['name']}"
            size = sum(f["size"] for f in group["files"])
            if key in state["done"]:
                continue
            if len(group["files"]) > FILES_MAX or size > FOLDER_MAX:
                count = len(group["files"])
                print(f"   ✗ {group['name']} : trop gros ({count} fichiers, {size >> 20} Mo), à la main")
                totals["erreurs"] += 1
                continue
            if args.liste:
                print(f"   · {group['name']} ({len(group['files'])} fichiers, {size >> 20} Mo)")
                continue
            try:
                result = upload(client, group)
            except Exception as exc:  # noqa: BLE001 - on continue avec les autres produits
                print(f"   ✗ {group['name']} : {exc}")
                totals["erreurs"] += 1
                continue
            state["done"][key] = result["id"]
            save_state(state)
            totals["produits"] += 1
            totals["fichiers"] += result["sent"]
            totals["deja"] += result["reused"]
            note = f", {result['reused']} déjà sur le serveur" if result["reused"] else ""
            print(f"   ✓ {group['name']} : {result['sent']} envoyés{note}")
            time.sleep(args.pause)
    print(
        f"\nTerminé : {totals['produits']} produits envoyés ({totals['fichiers']} fichiers, "
        f"{totals['deja']} déjà présents), {totals['erreurs']} en erreur."
    )
    print("L'analyse et le rangement continuent sur le serveur : suivez-les dans « Import de dossiers AMM ».")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompu : relancez la même commande pour reprendre.")
        sys.exit(130)
