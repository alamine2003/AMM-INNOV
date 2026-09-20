"""ZIP of a document set, files named `{ISO2}_{PRODUIT}_{KIND}_{AAAA-MM-JJ}.pdf` and written in
the canonical order (most recent first).

Produit au fil de l'eau (campagne de chaos s08) : le ZIP était assemblé en mémoire ; huit
archives simultanées de scans réels faisaient passer le processus web de 659 à 872 Mio puis le
tuaient, avec les requêtes des autres utilisateurs. L'écrire dans un fichier temporaire ne
suffisait pas : le cache disque est compté dans la mémoire du conteneur (pic mesuré au plafond de
1 Go). Chaque bloc part désormais vers le client dès qu'il est écrit. Scans stockés sans
recompression : un PDF scanné est déjà compressé.
"""

import io
import zipfile

from asgiref.sync import sync_to_async

CHUNK = 1024 * 1024


class _Outbox(io.RawIOBase):
    """Sortie non adressable du ZIP, vidée à chaque bloc (zipfile écrit alors des descripteurs)."""

    def __init__(self):
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def drain(self) -> bytes:
        out = b"".join(self._chunks)
        self._chunks.clear()
        return out


def _named(documents):
    used: dict[str, int] = {}
    for document in documents:
        name = document.export_filename()
        if name in used:
            used[name] += 1
            stem, ext = name.rsplit(".", 1)
            name = f"{stem}_{used[name]}.{ext}"
        else:
            used[name] = 1
        yield name, document


def iter_archive(documents):
    """Blocs successifs du ZIP ; la mémoire reste bornée à quelques blocs."""
    outbox = _Outbox()
    with zipfile.ZipFile(outbox, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, document in _named(documents):
            document.file.open("rb")
            try:
                with archive.open(name, "w", force_zip64=True) as entry:
                    while chunk := document.file.read(CHUNK):
                        entry.write(chunk)
                        yield outbox.drain()
            finally:
                document.file.close()
    yield outbox.drain()


async def aiter_blocks(first: bytes, stream):
    """Le même flux, en itérateur asynchrone, pour un serveur ASGI.

    Sous ASGI, Django lit un itérateur synchrone en entier (`sync_to_async(list)`) avant
    d'envoyer le premier octet : le ZIP « en flux » revenait tout entier en mémoire (s08 rejoué,
    processus web tué à nouveau). Ici chaque bloc est tiré à part, dans le fil de la requête.
    """
    try:
        if first:
            yield first
        while (block := await sync_to_async(next)(stream, None)) is not None:
            if block:
                yield block
    finally:
        await sync_to_async(stream.close)()  # client parti : le scan ouvert est refermé


def build_archive(documents) -> bytes:
    """Archive complète en mémoire, pour les petits lots (tests, scripts)."""
    return b"".join(iter_archive(documents))
