"""Lecture du classement AMM GHPL sur Nextcloud, en WebDAV, sans jamais rien y écrire.

Deux requêtes seulement : PROPFIND (profondeur 0 : version et taille d'un fichier) et GET.
L'identifiant et le mot de passe d'application viennent des réglages (variables d'environnement
saisies dans Render) ; ils ne sont ni journalisés ni renvoyés par l'API.
"""

from __future__ import annotations

import base64
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree

DAV = "{DAV:}"
CHUNK = 1 << 20


class NextcloudError(Exception):
    """Nextcloud injoignable ou réponse inattendue (message en français, sans secret)."""


class TooLarge(NextcloudError):
    pass


@dataclass
class RemoteFile:
    path: str
    etag: str
    size: int
    modified: datetime | None


class Nextcloud:
    def __init__(self, base_url: str, user: str, password: str, root: str, timeout: int = 90):
        self.base = base_url.rstrip("/")
        self.user = user
        self.root = root.strip("/")
        self.timeout = timeout
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._auth = f"Basic {token}"

    @classmethod
    def from_settings(cls) -> Nextcloud | None:
        from django.conf import settings

        if not (
            settings.NEXTCLOUD_URL and settings.NEXTCLOUD_USER and settings.NEXTCLOUD_APP_PASSWORD
        ):
            return None
        return cls(
            settings.NEXTCLOUD_URL,
            settings.NEXTCLOUD_USER,
            settings.NEXTCLOUD_APP_PASSWORD,
            settings.GHPL_SYNC_ROOT,
        )

    def url(self, path: str) -> str:
        parts = [self.user, *self.root.split("/"), *path.strip("/").split("/")]
        quoted = "/".join(urllib.parse.quote(part, safe="") for part in parts if part)
        return f"{self.base}/remote.php/dav/files/{quoted}"

    def _open(self, method: str, path: str, headers: dict | None = None, body: bytes | None = None):
        request = urllib.request.Request(
            self.url(path),
            data=body,
            method=method,
            headers={"Authorization": self._auth, **(headers or {})},
        )
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code in (401, 403):
                raise NextcloudError(
                    "Nextcloud refuse la connexion : vérifiez l'identifiant et le mot de passe "
                    "d'application (variables NEXTCLOUD_USER et NEXTCLOUD_APP_PASSWORD)."
                ) from None
            raise NextcloudError(f"Nextcloud a répondu {error.code} pour « {path} ».") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise NextcloudError(f"Nextcloud injoignable ({reason}).") from None

    def stat(self, path: str) -> RemoteFile | None:
        """Version (ETag), taille et date d'un fichier ; None s'il n'existe pas."""
        body = (
            b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
            b"<d:getetag/><d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>"
        )
        response = self._open(
            "PROPFIND", path, {"Depth": "0", "Content-Type": "application/xml"}, body
        )
        if response is None:
            return None
        with response:
            tree = ElementTree.fromstring(response.read())
        prop = tree.find(f".//{DAV}prop")
        if prop is None:
            raise NextcloudError(f"Réponse WebDAV illisible pour « {path} ».")

        def text(name: str) -> str:
            node = prop.find(f"{DAV}{name}")
            return (node.text or "").strip() if node is not None else ""

        modified = text("getlastmodified")
        try:
            when = parsedate_to_datetime(modified) if modified else None
        except (TypeError, ValueError):
            when = None
        return RemoteFile(
            path=path,
            etag=text("getetag").strip('"'),
            size=int(text("getcontentlength") or 0),
            modified=when,
        )

    def download(self, path: str, max_bytes: int) -> bytes | None:
        """Contenu du fichier (None s'il n'existe plus) ; TooLarge au-delà de `max_bytes`."""
        response = self._open("GET", path)
        if response is None:
            return None
        with response:
            length = int(response.headers.get("Content-Length") or 0)
            if length > max_bytes:
                raise TooLarge(f"{length >> 20} Mo")
            chunks, total = [], 0
            while block := response.read(CHUNK):
                total += len(block)
                if total > max_bytes:
                    raise TooLarge(f"plus de {max_bytes >> 20} Mo")
                chunks.append(block)
        return b"".join(chunks)
