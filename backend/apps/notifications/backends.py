"""Envoi des e-mails par l'API Gmail (HTTPS).

Railway bloque les ports SMTP sortants (25, 465, 587, 2525) : aucun serveur SMTP n'est
joignable depuis les conteneurs. L'API Gmail passe par le port 443, ouvert.

Authentification OAuth2 avec un jeton de rafraîchissement obtenu une fois pour toutes
(portée `gmail.send`), échangé contre un jeton d'accès d'une heure, mis en cache par processus.
Trois variables : `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`.
Activation : `EMAIL_URL=gmail://`.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
TIMEOUT = 20


class GmailConfigurationError(RuntimeError):
    """Identifiants OAuth absents ou refusés par Google."""


def _post(url: str, *, data: bytes, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode(errors="replace")
        raise GmailConfigurationError(f"Gmail a répondu {exc.code} : {detail}") from exc


class GmailApiBackend(BaseEmailBackend):
    """Backend e-mail Django s'appuyant sur `users.messages.send` de l'API Gmail."""

    def __init__(self, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.client_id = getattr(settings, "GMAIL_CLIENT_ID", "") or ""
        self.client_secret = getattr(settings, "GMAIL_CLIENT_SECRET", "") or ""
        self.refresh_token = getattr(settings, "GMAIL_REFRESH_TOKEN", "") or ""
        self._token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    # --- OAuth2

    def access_token(self) -> str:
        """Jeton d'accès valide, renouvelé au besoin (cache par processus)."""
        with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            missing = [
                name
                for name, value in (
                    ("GMAIL_CLIENT_ID", self.client_id),
                    ("GMAIL_CLIENT_SECRET", self.client_secret),
                    ("GMAIL_REFRESH_TOKEN", self.refresh_token),
                )
                if not value
            ]
            if missing:
                raise GmailConfigurationError(
                    "Identifiants Gmail incomplets : " + ", ".join(missing)
                )
            payload = urllib.parse.urlencode(
                {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                }
            ).encode()
            data = _post(
                TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            self._token = data.get("access_token", "")
            if not self._token:
                raise GmailConfigurationError("Google n'a pas renvoyé de jeton d'accès.")
            # marge d'une minute avant l'expiration annoncée
            self._expires_at = time.monotonic() + max(int(data.get("expires_in", 3600)) - 60, 0)
            return self._token

    # --- API Django

    def send_messages(self, email_messages) -> int:
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                logger.exception("Envoi Gmail impossible vers %s", getattr(message, "to", "?"))
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message) -> None:
        raw = base64.urlsafe_b64encode(message.message().as_bytes()).decode()
        _post(
            SEND_URL,
            data=json.dumps({"raw": raw}).encode(),
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json",
            },
        )
