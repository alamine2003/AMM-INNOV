"""1.3.4 : un scan est envoyé bloc par bloc, il ne revient plus tout entier en mémoire.

Constat du 18/11/2026 sur le serveur : l'API tenait 992 Mo sur 1 Go après 19 heures. Sous ASGI,
Django lit un itérateur synchrone en entier avant d'envoyer le premier octet ; chaque scan
affiché passait donc tout entier par la mémoire du processus web, en blocs de 4 Ko.
"""

import asyncio
import io
import re
import warnings
from pathlib import Path

import pytest

from apps.documents.views import StoredFileResponse

ROOT = Path(__file__).resolve().parents[2]
BLOCK = StoredFileResponse.block_size


class CountingFile(io.BytesIO):
    """Fichier qui note chaque lecture et sa fermeture."""

    def __init__(self, content: bytes):
        super().__init__(content)
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        return super().read(size)


@pytest.mark.django_db  # response.close() signale la fin de requête à Django
def test_scan_blocks_are_pulled_one_at_a_time_under_asgi():
    """Le client lit deux blocs puis s'en va (page tournée) : le reste du scan n'est pas lu."""
    scan = CountingFile(b"s" * (20 * BLOCK))
    response = StoredFileResponse(scan, content_type="application/pdf")

    async def client_reads_two_blocks_then_leaves():
        blocks = aiter(response)
        received = [await anext(blocks), await anext(blocks)]
        await blocks.aclose()
        return received

    with warnings.catch_warnings():
        # Django prévient quand il doit lire tout l'itérateur d'un coup : ce serait une régression.
        warnings.simplefilter("error")
        received = asyncio.run(client_reads_two_blocks_then_leaves())

    assert [len(block) for block in received] == [BLOCK, BLOCK]
    assert scan.reads == 2
    response.close()
    assert scan.closed


def test_scan_is_complete_under_asgi_and_wsgi():
    content = bytes(range(256)) * (10 * 1024)  # 2,5 Mo : plusieurs blocs, le dernier incomplet

    async def read_all(response):
        return [block async for block in response]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        asgi = asyncio.run(
            read_all(StoredFileResponse(io.BytesIO(content), content_type="application/pdf"))
        )
    wsgi = list(StoredFileResponse(io.BytesIO(content), content_type="application/pdf"))

    assert b"".join(asgi) == content
    assert b"".join(wsgi) == content
    assert len(asgi) == len(wsgi) == -(-len(content) // BLOCK)
    assert max(len(block) for block in asgi) == BLOCK


def test_no_view_sends_a_file_with_plain_fileresponse():
    """Toute vue qui envoie un fichier passe par StoredFileResponse."""
    plain = re.compile(r"(?<![A-Za-z])FileResponse\(")
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in (ROOT / "backend" / "apps").rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if plain.search(line) and not line.startswith("class StoredFileResponse(")
    ]
    assert offenders == []


def test_web_server_gives_freed_memory_back():
    """Les deux réglages de glibc sont posés avant le lancement du serveur web."""
    script = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    server = script.index("exec uvicorn")
    for setting in (
        'export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"',
        "export MALLOC_MMAP_THRESHOLD_=",
    ):
        assert 0 <= script.rfind(setting, 0, server), setting
