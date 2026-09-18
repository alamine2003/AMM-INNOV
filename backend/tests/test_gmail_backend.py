"""Backend e-mail Gmail (API HTTPS) : jeton, cache, envoi, erreurs."""

import base64
import json
from email import message_from_bytes

import pytest
from django.core.mail import EmailMessage, send_mail
from django.test import override_settings

from apps.notifications.backends import GmailApiBackend, GmailConfigurationError

GMAIL_SETTINGS = {
    "EMAIL_BACKEND": "apps.notifications.backends.GmailApiBackend",
    "GMAIL_CLIENT_ID": "client-1.apps.googleusercontent.com",
    "GMAIL_CLIENT_SECRET": "secret-1",
    "GMAIL_REFRESH_TOKEN": "refresh-1",
    "DEFAULT_FROM_EMAIL": "AMM INNOV <regulatoire@example.com>",
}


class FakeGoogle:
    """Remplace les appels HTTP vers Google et enregistre ce qui est envoyé."""

    def __init__(self, token_expires_in=3600, send_error=None):
        self.calls = []
        self.token_calls = 0
        self.token_expires_in = token_expires_in
        self.send_error = send_error

    def __call__(self, url, *, data, headers):
        self.calls.append({"url": url, "data": data, "headers": headers})
        if url.endswith("/token"):
            self.token_calls += 1
            return {
                "access_token": f"jeton-{self.token_calls}",
                "expires_in": self.token_expires_in,
            }
        if self.send_error:
            raise self.send_error
        return {"id": "msg-1"}

    def sent_messages(self):
        out = []
        for call in self.calls:
            if call["url"].endswith("/send"):
                raw = json.loads(call["data"])["raw"]
                out.append(message_from_bytes(base64.urlsafe_b64decode(raw)))
        return out


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr("apps.notifications.backends._post", fake)
    return fake


def test_message_is_sent_through_the_api(google):
    with override_settings(**GMAIL_SETTINGS):
        count = send_mail(
            "Alerte J-180", "Corps du message", None, ["pays@example.com"], fail_silently=False
        )
    assert count == 1
    messages = google.sent_messages()
    assert len(messages) == 1
    assert messages[0]["To"] == "pays@example.com"
    assert messages[0]["Subject"] == "Alerte J-180"
    assert messages[0]["From"] == "AMM INNOV <regulatoire@example.com>"
    assert "Corps du message" in messages[0].get_payload()
    # le jeton d'accès accompagne l'envoi
    send_call = google.calls[-1]
    assert send_call["headers"]["Authorization"] == "Bearer jeton-1"


@pytest.fixture(autouse=True)
def fresh_token_cache():
    GmailApiBackend.reset_token_cache()
    yield
    GmailApiBackend.reset_token_cache()


def test_access_token_is_shared_across_send_mail_calls(google):
    """send_mail() crée un backend par message : le jeton doit survivre à l'instance."""
    with override_settings(**GMAIL_SETTINGS):
        send_mail("un", "a", None, ["x@example.com"])
        send_mail("deux", "b", None, ["y@example.com"])
    assert google.token_calls == 1
    assert len(google.sent_messages()) == 2


def test_access_token_is_reused_across_messages(google):
    with override_settings(**GMAIL_SETTINGS):
        backend = GmailApiBackend()
        backend.send_messages(
            [EmailMessage("un", "a", None, ["x@example.com"]),
             EmailMessage("deux", "b", None, ["y@example.com"])]
        )
    assert google.token_calls == 1  # un seul échange OAuth pour deux messages
    assert len(google.sent_messages()) == 2


def test_expired_token_is_renewed(monkeypatch):
    fake = FakeGoogle(token_expires_in=0)  # expire immédiatement
    monkeypatch.setattr("apps.notifications.backends._post", fake)
    with override_settings(**GMAIL_SETTINGS):
        backend = GmailApiBackend()
        backend.send_messages([EmailMessage("un", "a", None, ["x@example.com"])])
        backend.send_messages([EmailMessage("deux", "b", None, ["y@example.com"])])
    assert fake.token_calls == 2


def test_missing_credentials_are_named():
    with override_settings(**{**GMAIL_SETTINGS, "GMAIL_REFRESH_TOKEN": ""}):
        with pytest.raises(GmailConfigurationError, match="GMAIL_REFRESH_TOKEN"):
            GmailApiBackend().send_messages([EmailMessage("x", "y", None, ["z@example.com"])])


def test_failure_is_swallowed_when_asked(monkeypatch):
    fake = FakeGoogle(send_error=GmailConfigurationError("Gmail a répondu 403"))
    monkeypatch.setattr("apps.notifications.backends._post", fake)
    with override_settings(**GMAIL_SETTINGS):
        assert GmailApiBackend(fail_silently=True).send_messages(
            [EmailMessage("x", "y", None, ["z@example.com"])]
        ) == 0
        with pytest.raises(GmailConfigurationError):
            GmailApiBackend().send_messages([EmailMessage("x", "y", None, ["z@example.com"])])


def test_email_url_selects_the_gmail_backend():
    from config.settings.base import parse_email_url

    assert parse_email_url("gmail://")["EMAIL_BACKEND"].endswith("GmailApiBackend")
    assert parse_email_url("gmail+api://")["EMAIL_BACKEND"].endswith("GmailApiBackend")
