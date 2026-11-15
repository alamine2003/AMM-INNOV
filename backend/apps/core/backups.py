"""Sauvegardes de la base sur un serveur (palier 1.3.0) : copie hors machine et surveillance.

Sur un serveur (docker-compose.partage.yml), le service `backup` écrit chaque nuit une
sauvegarde chiffrée et vérifiée dans BACKUP_DIR (`scripts/serveur/sauvegarder.sh`), avec un
fichier `etat.json`. Le worker lit ce dossier en lecture seule :
 - `copy_offsite` copie les sauvegardes vérifiées dans le stockage des scans (S3), sous
   `sauvegardes/base/` : la machine peut être perdue sans perdre la base ;
 - `backup_problems` dit ce qui ne va pas : sauvegarde en échec, trop ancienne, pas copiée.
Sans BACKUP_DIR (Render : la sauvegarde y est faite par GitHub Actions), rien n'est actif.
La phrase secrète n'est jamais connue de l'application : elle ne manipule que des fichiers
déjà chiffrés.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .integrity import ERROR, WARNING, Check

NAME = re.compile(r"^amm-vm-(\d{8}-\d{6})\.dump\.gpg$")
KEEP = 7  # la rotation ne retire jamais les 7 dernières, même anciennes


def made_at(name: str) -> datetime | None:
    """Date de la sauvegarde, lue dans son nom (UTC) ; None si ce n'est pas une sauvegarde."""
    match = NAME.match(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def local_state() -> dict | None:
    """Ce que la dernière sauvegarde a écrit dans etat.json ; None s'il est absent ou illisible."""
    try:
        state = json.loads((Path(settings.BACKUP_DIR) / "etat.json").read_text())
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def local_backups() -> list[Path]:
    """Sauvegardes vérifiées présentes sur le serveur, la plus récente d'abord."""
    try:
        paths = [p for p in Path(settings.BACKUP_DIR).iterdir() if p.is_file() and made_at(p.name)]
    except OSError:
        return []
    return sorted(paths, key=lambda p: p.name, reverse=True)


def remote_bucket():
    """Le stockage des scans quand il est sur S3 (hors de la machine) ; None en stockage local."""
    from django.core.files.storage import default_storage

    return getattr(default_storage, "bucket", None)


def remote_backups(bucket) -> dict:
    """{nom: objet} des sauvegardes déjà copiées hors de la machine."""
    prefix = settings.BACKUP_REMOTE_PREFIX
    found = {}
    for obj in bucket.objects.filter(Prefix=prefix):
        name = obj.key[len(prefix) :]
        if made_at(name):
            found[name] = obj
    return found


def copy_offsite() -> dict:
    """Copie hors machine chaque sauvegarde vérifiée qui n'y est pas encore, puis rotation.

    Rejouable : une sauvegarde déjà copiée n'est pas renvoyée. La rotation ne touche que des
    fichiers nommés comme des sauvegardes, sous leur préfixe, jamais les 7 plus récents.
    """
    bucket = remote_bucket()
    if bucket is None:
        return {"active": False, "copied": [], "removed": []}
    prefix = settings.BACKUP_REMOTE_PREFIX
    remote = remote_backups(bucket)
    local = {path.name: path for path in local_backups()}
    # Périmées : au-delà de la rétention, hors des 7 plus récentes. Jugé sur l'ensemble (serveur
    # et copie) : une sauvegarde périmée encore sur le serveur n'est pas renvoyée chaque heure.
    limit = timezone.now() - timedelta(days=settings.BACKUP_REMOTE_RETENTION_DAYS)
    names = sorted({*remote, *local}, reverse=True)
    expired = {name for name in names[KEEP:] if made_at(name) < limit}
    copied = []
    for name in sorted(set(local) - set(remote) - expired):
        path, key = local[name], prefix + name
        bucket.upload_file(str(path), key)
        sent = bucket.Object(key)
        if sent.content_length != path.stat().st_size:
            raise OSError(f"copie incomplète de {name} : {sent.content_length} octets reçus")
        copied.append(name)
    removed = []
    for name in sorted(expired & set(remote)):
        remote[name].delete()
        removed.append(name)
    return {"active": True, "copied": copied, "removed": removed}


def _late(names, limit: timedelta) -> str | None:
    """Phrase si la plus récente sauvegarde de `names` est absente ou trop ancienne."""
    newest = max((made_at(name) for name in names), default=None)
    if newest is None:
        return "aucune sauvegarde vérifiée"
    if timezone.now() - newest > limit:
        hours = int(limit.total_seconds() // 3600)
        return f"la dernière date du {newest:%d/%m/%Y à %H:%M} UTC, plus de {hours} heures"
    return None


def local_problems() -> list[str]:
    """Sur le serveur : la sauvegarde de la nuit a-t-elle tourné, réussi, été relue ?"""
    if not settings.BACKUP_DIR:
        return []
    state = local_state()
    if state is None:
        return ["Aucune sauvegarde n'a encore tourné sur ce serveur (etat.json absent)."]
    found = []
    if not state.get("ok"):
        found.append(
            f"La dernière sauvegarde a échoué ({state.get('at', '?')}) : "
            f"{state.get('error') or 'cause inconnue'}."
        )
    late = _late([p.name for p in local_backups()], timedelta(hours=settings.BACKUP_MAX_AGE_HOURS))
    if late:
        found.append(f"Sauvegarde sur le serveur : {late}.")
    return found


def offsite_problems() -> list[str]:
    """Hors de la machine : la copie suit-elle ? (une heure de marge sur la copie horaire)"""
    if not settings.BACKUP_DIR:
        return []
    try:
        bucket = remote_bucket()
        if bucket is None:
            return [
                "Les sauvegardes ne quittent pas le serveur : le stockage S3 n'est pas configuré "
                "(DOCUMENT_STORAGE=s3). Si la machine est perdue, la base l'est aussi."
            ]
        names = list(remote_backups(bucket))
    except Exception as exc:  # réseau, droits : le constat est le même, la copie n'est pas sûre
        return [f"Le stockage hors du serveur ne répond pas : {exc}."]
    late = _late(names, timedelta(hours=settings.BACKUP_MAX_AGE_HOURS + 1))
    return [f"Copie hors du serveur : {late}."] if late else []


def backup_problems() -> list[str]:
    return local_problems() + offsite_problems()


def check_backups(options) -> list[Check]:
    """Déclaré au registre INTEGRITY par apps/administration/hooks.py."""
    local = Check(
        "backup_verified",
        ERROR,
        f"La base a-t-elle une sauvegarde vérifiée de moins de {settings.BACKUP_MAX_AGE_HOURS} h ?",
    )
    offsite = Check(
        "backup_offsite", WARNING, "La dernière sauvegarde est-elle copiée hors du serveur ?"
    )
    for item in local_problems():
        local.add(item)
    if not options.skip_storage:
        for item in offsite_problems():
            offsite.add(item)
    return [local, offsite]
