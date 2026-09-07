#!/usr/bin/env python3
"""Obtient le jeton de rafraîchissement OAuth2 pour l'envoi d'e-mails par l'API Gmail.

À lancer une seule fois, depuis un poste avec un navigateur :

    python3 scripts/gmail_oauth.py --client-id <ID> --client-secret <SECRET>

Le script ouvre une page de consentement Google, récupère le code d'autorisation sur
`http://localhost:<port>` (accepté d'office pour un client OAuth de type « Application de
bureau »), puis affiche le jeton de rafraîchissement à placer dans `GMAIL_REFRESH_TOKEN`.

Portée demandée : `gmail.send` uniquement — l'application peut envoyer, jamais lire.
"""

from __future__ import annotations

import argparse
import http.server
import json
import secrets
import socket
import threading
import urllib.parse
import urllib.request
import webbrowser

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/gmail.send"

PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<title>AMM INNOV</title>
<body style="font-family:system-ui;padding:3rem;max-width:34rem;margin:auto">
<h1>Autorisation enregistrée</h1>
<p>{message}</p><p>Vous pouvez fermer cet onglet et revenir au terminal.</p></body></html>"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Handler(http.server.BaseHTTPRequestHandler):
    result: dict = {}
    expected_state = ""

    def do_GET(self):  # noqa: N802 (nom imposé par http.server)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        error = (query.get("error") or [""])[0]
        if error:
            message = f"Google a renvoyé une erreur : {error}"
        elif state != Handler.expected_state:
            message = "État inattendu : demande ignorée."
        elif code:
            Handler.result["code"] = code
            message = "Le jeton va être récupéré dans le terminal."
        else:
            message = "Aucun code reçu."
        body = PAGE.format(message=message).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--port", type=int, default=0, help="port local (0 = au hasard)")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    port = args.port or free_port()
    redirect_uri = f"http://localhost:{port}"
    Handler.expected_state = secrets.token_urlsafe(16)

    params = {
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # indispensable pour obtenir un refresh_token
        "prompt": "consent",          # force un nouveau refresh_token même si déjà autorisé
        "state": Handler.expected_state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("\nOuvrez cette adresse dans votre navigateur, connectez-vous avec le compte")
    print("expéditeur, puis autorisez « Envoyer un e-mail en votre nom » :\n")
    print(url + "\n")
    if not args.no_browser:
        webbrowser.open(url)
    print(f"En attente du retour de Google sur {redirect_uri} …")

    deadline = threading.Event()
    while "code" not in Handler.result and not deadline.wait(1):
        pass
    server.shutdown()

    payload = urllib.parse.urlencode(
        {
            "code": Handler.result["code"],
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    request = urllib.request.Request(
        TOKEN_URL, data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read())

    refresh = data.get("refresh_token")
    if not refresh:
        print("Google n'a pas renvoyé de jeton de rafraîchissement.")
        print("Retirez l'accès sur https://myaccount.google.com/permissions puis recommencez.")
        return 1
    print("\nGMAIL_REFRESH_TOKEN=" + refresh)
    print("\nÀ placer dans les variables du service, avec GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET")
    print("et EMAIL_URL=gmail://")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
