"""1.3.5 : les scans sont servis par nginx, l'API n'en vérifie plus que le droit de lecture.

L'API répond sans corps, avec `X-Accel-Redirect` vers l'emplacement nommé de docker/nginx.conf
et une adresse signée du stockage S3 que le navigateur ne voit jamais. L'essai de bout en bout
(nginx réel, stockage S3 d'essai) est décrit dans CHANGELOG.md ; ici, le contrat des deux côtés.
"""

import io
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from django.test import override_settings

from apps.core.exceptions import StorageUnavailable, StoredFileLost
from apps.documents import views
from apps.documents.views import ACCEL_LOCATION, StoredFileResponse, stored_file_response

ROOT = Path(__file__).resolve().parents[2]
SIGNED = "https://stockage.example/amm/scans/d%C3%A9cision%201.pdf?X-Amz-Signature=abc"

pytestmark = pytest.mark.django_db


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.heads = []
        self.signed = []

    def head_object(self, **kwargs):
        self.heads.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"ContentLength": 3}

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803 — boto3
        self.signed.append((operation, Params, ExpiresIn))
        return SIGNED


class FakeS3Storage:
    """Ce que l'API utilise d'un stockage S3 : le bucket, le nom de l'objet, la connexion."""

    bucket_name = "amm"

    def __init__(self, client):
        self.client = client
        self.connections_built = 0

    @property
    def connection(self):
        self.connections_built += 1  # django-storages en reconstruit une par fil
        return SimpleNamespace(meta=SimpleNamespace(client=self.client))

    def _normalize_name(self, name):
        return name


def s3_file(client=None, name="scans/décision 1.pdf"):
    return SimpleNamespace(name=name, storage=FakeS3Storage(client or FakeClient()))


def local_file(content=b"%PDF-1.4 local"):
    stream = io.BytesIO(content)
    stream.name = "scans/local.pdf"
    stream.storage = SimpleNamespace(exists=lambda name: True)
    stream.open = lambda mode="rb": stream
    return stream


def not_found():
    return ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
    )


@override_settings(DOCUMENT_ACCEL_REDIRECT=True, DOCUMENT_ACCEL_URL_SECONDS=120)
def test_scan_is_handed_over_to_nginx_without_a_body():
    scan = s3_file()
    response = stored_file_response(
        scan, content_type="application/pdf", as_attachment=True, filename="Décision 1.pdf"
    )

    assert response.status_code == 200
    assert response.content == b""
    assert response["X-Accel-Redirect"] == ACCEL_LOCATION
    assert response["X-Storage-Url"] == SIGNED
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment; filename")
    client = scan.storage.client
    assert client.heads == [{"Bucket": "amm", "Key": "scans/décision 1.pdf"}]
    assert client.signed == [("get_object", {"Bucket": "amm", "Key": "scans/décision 1.pdf"}, 120)]


@override_settings(DOCUMENT_ACCEL_REDIRECT=True)
def test_content_type_is_guessed_from_the_name_when_unknown():
    response = stored_file_response(s3_file(), filename="accusé.pdf")
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline; filename")


@override_settings(DOCUMENT_ACCEL_REDIRECT=True)
def test_missing_scan_is_a_410_before_nginx_is_involved():
    with pytest.raises(StoredFileLost):
        stored_file_response(s3_file(FakeClient(not_found())), content_type="application/pdf")


@override_settings(DOCUMENT_ACCEL_REDIRECT=True)
def test_storage_down_is_a_503_before_nginx_is_involved():
    for error in (
        ConnectionError("stockage injoignable"),
        ClientError({"Error": {"Code": "500"}, "ResponseMetadata": {"HTTPStatusCode": 500}}, "H"),
    ):
        with pytest.raises(StorageUnavailable):
            stored_file_response(s3_file(FakeClient(error)), content_type="application/pdf")


@override_settings(DOCUMENT_ACCEL_REDIRECT=False)
def test_without_nginx_in_front_the_api_sends_the_scan_itself():
    """Réglage coupé (Render, retour arrière) : le fichier part bloc par bloc, comme en 1.3.4."""
    scan = s3_file()
    scan.open = lambda mode="rb": None
    scan.read = io.BytesIO(b"%PDF-1.4 contenu").read
    response = stored_file_response(scan, content_type="application/pdf")

    assert isinstance(response, StoredFileResponse)
    assert "X-Accel-Redirect" not in response
    assert b"".join(response) == b"%PDF-1.4 contenu"
    assert scan.storage.client.signed == []


@override_settings(DOCUMENT_ACCEL_REDIRECT=True)
def test_a_file_on_disk_is_never_handed_over_to_nginx():
    response = stored_file_response(local_file(), content_type="application/pdf")
    assert isinstance(response, StoredFileResponse)
    assert "X-Accel-Redirect" not in response


@override_settings(DOCUMENT_ACCEL_REDIRECT=True)
def test_one_s3_client_serves_every_request_thread():
    """Sous ASGI chaque requête a un fil neuf : la connexion S3 n'est construite qu'une fois."""
    scan = s3_file()
    errors = []

    def request():
        try:
            stored_file_response(scan, content_type="application/pdf")
        except Exception as exc:  # noqa: BLE001 — remonté par l'assertion
            errors.append(exc)

    for _ in range(20):
        thread = threading.Thread(target=request)
        thread.start()
        thread.join()

    assert errors == []
    assert len(scan.storage.client.heads) == 20
    assert scan.storage.connections_built == 1


def test_accel_is_off_by_default_and_on_behind_the_frontend_nginx():
    from django.conf import settings

    assert settings.DOCUMENT_ACCEL_REDIRECT is False
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "DOCUMENT_ACCEL_REDIRECT: ${DOCUMENT_ACCEL_REDIRECT:-1}" in compose


def test_nginx_location_matches_what_the_api_sends():
    conf = (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")
    block = re.search(rf"location {re.escape(ACCEL_LOCATION)} \{{(.*?)\n    \}}", conf, re.S)
    assert block, f"emplacement {ACCEL_LOCATION} absent de docker/nginx.conf"
    body = block.group(1)
    for expected in (
        "set $storage_url $upstream_http_x_storage_url;",
        "proxy_pass $storage_url;",
        'proxy_set_header Authorization "";',  # le stockage refuse jeton + signature
        "add_header Access-Control-Allow-Origin $cors_origin always;",
        "add_header Content-Security-Policy $file_csp always;",
        "add_header X-Content-Type-Options nosniff always;",
        "proxy_intercept_errors on;",
    ):
        assert expected in body, expected
    # Emplacement nommé : aucune adresse ne permet de l'appeler de l'extérieur.
    assert ACCEL_LOCATION.startswith("@")


def test_storage_is_read_over_verified_https_with_v4_signatures():
    conf = (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")
    for expected in ("proxy_ssl_verify on;", "proxy_ssl_server_name on;", "proxy_method GET;"):
        assert expected in conf, expected
    # Cloudflare R2 n'accepte que la signature V4 ; boto3 signe encore des adresses en V2.
    settings_source = (ROOT / "backend" / "config" / "settings" / "base.py").read_text("utf-8")
    assert 'signature_version="s3v4",' in settings_source


def test_views_send_files_through_the_single_entry_point():
    """Aucune vue n'ouvre ni n'envoie un fichier elle-même : tout passe par stored_file_response."""
    direct = re.compile(r"(?<![A-Za-z_])(StoredFileResponse|FileResponse|open_stored_file)\(")
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in (ROOT / "backend" / "apps").rglob("*.py")
        if path != Path(views.__file__)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if direct.search(line)
    ]
    assert offenders == []
