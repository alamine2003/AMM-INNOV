#!/usr/bin/env python3
"""Envoie les scans du classement AMM GHPL dans AMM GH, à l'endroit fixé par l'import du manifeste.

Étape 3 de l'import du classement (après le Dashboard et le registre) :

1. Dans AMM GH, menu Imports Excel : importer « manifeste_scans_amm_gh.csv » (simulation d'abord,
   puis pour de bon). Chaque pièce principale y reçoit sa place : AMM, renouvellement, type, date.
2. Sur le Mac, ce script lit ces places et envoie chaque fichier (POST /amms/{id}/documents) :

       python3 importer_scans_classement.py --classement "~/…/AMM GHPL - CLASSEMENT GENERAL"

Python 3 du Mac suffit (bibliothèque standard seulement). Le mot de passe AMM GH est demandé une
fois (getpass) et reste en mémoire : il n'est ni affiché ni écrit. Le script peut être arrêté et
relancé : ce qui est déjà envoyé est noté dans `importer_scans_etat.json` et n'est pas renvoyé ;
un fichier déjà présent sur la fiche (même empreinte) est compté « déjà là ».

- Le fichier doit être celui du manifeste : son SHA-256 est vérifié avant l'envoi.
- .jp2 : converti en JPEG par `sips` (macOS) ; .docx : converti en PDF par LibreOffice s'il est
  installé, sinon laissé de côté ; plus de 25 Mo : laissé de côté (à compresser puis déposer
  à la main) ; tout est listé dans le rapport CSV.
- Render gratuit : réveil lent, coupures (502/503/504) ; le script attend et réessaie.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

API = "https://amm-innov-api.onrender.com/api/v1"
MAX_MB = 25
RETRY = (429, 500, 502, 503, 504)
TOKEN_TTL = 10 * 60  # le jeton d'accès vit 15 min : on se reconnecte avant
SUFFIXES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"{status} {body[:300]}")
        self.status, self.body = status, body


class Api:
    def __init__(self, base: str, email: str, password: str):
        self.base, self.email, self._password = base.rstrip("/"), email, password
        self.token, self.since = "", 0.0

    def _send(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        headers=None,
        timeout=300,
    ):
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        request = urllib.request.Request(
            url, data=data, method=method, headers=headers or {}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", "replace")

    def login(self) -> None:
        body = json.dumps({"email": self.email, "password": self._password}).encode()
        for attempt in range(8):
            try:
                status, text = self._send(
                    "POST",
                    "auth/login",
                    body,
                    {"Content-Type": "application/json"},
                    timeout=120,
                )
            except OSError as error:  # service endormi ou réseau
                status, text = 0, str(error)
            if status == 200:
                self.token, self.since = json.loads(text)["access"], time.monotonic()
                return
            if status in (400, 401, 403):
                raise SystemExit(
                    "Connexion refusée : vérifiez l'adresse et le mot de passe AMM GH."
                )
            wait = 15 * (attempt + 1)
            print(
                f"  connexion impossible ({status or text[:60]}), nouvel essai dans {wait} s"
            )
            time.sleep(wait)
        raise SystemExit("AMM GH ne répond pas : réessayez plus tard.")

    def call(self, method: str, path: str, data: bytes | None = None, headers=None):
        for attempt in range(8):
            if not self.token or time.monotonic() - self.since > TOKEN_TTL:
                self.login()
            all_headers = {"Authorization": f"Bearer {self.token}", **(headers or {})}
            try:
                status, text = self._send(method, path, data, all_headers)
            except OSError as error:
                status, text = 0, str(error)
            if status == 401:
                self.token = ""
                continue
            if status in RETRY or status == 0:
                wait = min(20 * (attempt + 1), 120)
                print(
                    f"  AMM GH indisponible ({status or text[:60]}), nouvel essai dans {wait} s"
                )
                time.sleep(wait)
                continue
            if status >= 400:
                raise ApiError(status, text)
            return json.loads(text) if text else {}
        raise ApiError(0, "AMM GH ne répond plus")


def multipart(fields: dict, filename: str, content: bytes, content_type: str):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    safe = filename.replace('"', "'")
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), {
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def prepare(path: Path, workdir: Path) -> tuple[Path | None, str, str]:
    """Fichier à envoyer, son type, ou (None, '', raison)."""
    suffix = path.suffix.lower()
    if suffix in SUFFIXES:
        return path, SUFFIXES[suffix], ""
    if suffix == ".jp2" and shutil.which("sips"):
        target = workdir / (path.stem + ".jpg")
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(path), "--out", str(target)],
            check=False,
            capture_output=True,
        )
        if target.exists():
            return target, "image/jpeg", ""
        return None, "", "conversion .jp2 impossible"
    if suffix == ".docx":
        office = (
            shutil.which("soffice")
            or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        )
        if Path(office).exists():
            subprocess.run(
                [
                    office,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(workdir),
                    str(path),
                ],
                check=False,
                capture_output=True,
                timeout=180,
            )
            target = workdir / (path.stem + ".pdf")
            if target.exists():
                return target, "application/pdf", ""
        return None, "", "Word (.docx) : à convertir en PDF (LibreOffice absent)"
    guess = mimetypes.guess_type(path.name)[0] or suffix or "sans extension"
    return None, "", f"format non accepté par AMM GH ({guess})"


def latest_scans_batch(api: Api) -> dict:
    page = api.call("GET", "imports?page_size=50")
    batches = page.get("results", page) if isinstance(page, dict) else page
    for batch in batches:
        summary = batch.get("summary") or {}
        if (
            summary.get("kind") == "scans"
            and not batch.get("dry_run")
            and batch["status"] == "DONE"
        ):
            return batch
    raise SystemExit(
        "Aucun import du manifeste (hors simulation) trouvé : importez d'abord "
        "« manifeste_scans_amm_gh.csv » dans Imports Excel, sans cocher Simulation."
    )


def rows_of(api: Api, batch_id: str) -> list[dict]:
    rows, url = [], f"imports/{batch_id}/rows?page_size=500"
    while url:
        page = api.call("GET", url)
        rows.extend(page["results"])
        url = page.get("next")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Envoie les scans classés dans AMM GH."
    )
    parser.add_argument(
        "--classement",
        required=True,
        type=Path,
        help="dossier « AMM GHPL - CLASSEMENT GENERAL »",
    )
    parser.add_argument("--email", help="adresse de connexion AMM GH")
    parser.add_argument("--api", default=os.environ.get("AMM_GH_API", API))
    parser.add_argument(
        "--lot", help="identifiant de l'import du manifeste (par défaut : le dernier)"
    )
    parser.add_argument("--etat", type=Path, default=Path("importer_scans_etat.json"))
    parser.add_argument(
        "--verifier", action="store_true", help="vérifie les fichiers sans rien envoyer"
    )
    parser.add_argument(
        "--pause", type=float, default=0.5, help="secondes entre deux envois"
    )
    args = parser.parse_args(argv)

    root = args.classement.expanduser()
    if not root.is_dir():
        raise SystemExit(f"Dossier introuvable : {root}")
    email = args.email or input("Adresse de connexion AMM GH : ").strip()
    api = Api(args.api, email, getpass.getpass("Mot de passe AMM GH (non affiché) : "))
    api.login()
    batch = {"id": args.lot} if args.lot else latest_scans_batch(api)
    if not args.lot:
        print(
            f"Import du manifeste retenu : {batch['id']} du {batch['created_at'][:16]}"
        )
    rows = [
        r for r in rows_of(api, batch["id"]) if (r.get("raw") or {}).get("placement")
    ]
    print(f"{len(rows)} pièces à ranger")

    state = (
        json.loads(args.etat.read_text(encoding="utf-8")) if args.etat.exists() else {}
    )
    report_path = Path(f"rapport_import_scans_{datetime.now().astimezone():%Y-%m-%d_%Hh%M-%S}.csv")
    counts: dict[str, int] = {}
    with (
        report_path.open("w", newline="", encoding="utf-8-sig") as handle,
        tempfile.TemporaryDirectory() as tmp,
    ):
        report = csv.writer(handle, delimiter=";")
        report.writerow(["Chemin", "Résultat", "Détail"])
        for index, row in enumerate(rows, start=1):
            raw, place = row["raw"], row["raw"]["placement"]
            key = f"{raw['chemin']}|{place['amm']}"
            if state.get(key) in {"envoyé", "déjà là"}:
                counts["déjà fait"] = counts.get("déjà fait", 0) + 1
                continue
            path = root / raw["chemin"]
            result, detail = "", ""
            if not path.is_file():
                result, detail = "absent", "fichier introuvable dans le classement"
            elif raw.get("sha256") and sha256(path) != raw["sha256"].lower():
                result, detail = "modifié", "le fichier a changé depuis le manifeste"
            else:
                sendable, content_type, reason = prepare(path, Path(tmp))
                if sendable is None:
                    result, detail = "laissé de côté", reason
                elif sendable.stat().st_size > MAX_MB * 1024 * 1024:
                    size = sendable.stat().st_size >> 20
                    result, detail = (
                        "laissé de côté",
                        f"{size} Mo > {MAX_MB} Mo : à compresser",
                    )
                elif args.verifier:
                    result, detail = "prêt", place["target"]
                else:
                    body, headers = multipart(
                        {
                            "kind": place["kind"],
                            "document_date": place["document_date"],
                            "title": place["title"],
                            "renewal": place.get("renewal"),
                        },
                        sendable.name,
                        sendable.read_bytes(),
                        content_type,
                    )
                    try:
                        api.call(
                            "POST", f"amms/{place['amm']}/documents", body, headers
                        )
                        result, detail = "envoyé", place["target"]
                    except ApiError as error:
                        if "existe déjà" in error.body:
                            result, detail = "déjà là", "même fichier déjà sur la fiche"
                        else:
                            result, detail = "erreur", str(error)
                    time.sleep(args.pause)
            counts[result] = counts.get(result, 0) + 1
            report.writerow([raw["chemin"], result, detail])
            if result in {"envoyé", "déjà là"}:
                state[key] = result
                if index % 20 == 0:
                    args.etat.write_text(
                        json.dumps(state, ensure_ascii=False), encoding="utf-8"
                    )
            if index % 25 == 0 or result == "erreur":
                print(f"[{index}/{len(rows)}] {result} — {raw['chemin'][-90:]}")
    args.etat.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print("Bilan :", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"Rapport : {report_path.resolve()}")
    return 0 if not counts.get("erreur") else 1


if __name__ == "__main__":
    sys.exit(main())
