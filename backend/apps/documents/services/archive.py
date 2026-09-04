"""In-memory ZIP of a document set, files named `{ISO2}_{PRODUIT}_{KIND}_{AAAA-MM-JJ}.pdf`
and written in the canonical order (most recent first)."""

import io
import zipfile


def build_archive(documents) -> bytes:
    buffer = io.BytesIO()
    used: dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for document in documents:
            name = document.export_filename()
            if name in used:
                used[name] += 1
                stem, ext = name.rsplit(".", 1)
                name = f"{stem}_{used[name]}.{ext}"
            else:
                used[name] = 1
            document.file.open("rb")
            try:
                archive.writestr(name, document.file.read())
            finally:
                document.file.close()
    return buffer.getvalue()
