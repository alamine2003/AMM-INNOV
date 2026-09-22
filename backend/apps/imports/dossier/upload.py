"""Validate a browser folder selection and stage immutable original documents.

The submitted relative path is descriptive metadata only. Storage keys are generated
by the model, never built from a client filename. No regulatory records are changed.
"""

import hashlib
import io
import logging
import re
import shlex
import subprocess
import tempfile
import unicodedata
import warnings
from dataclasses import dataclass
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from apps.imports.models import DossierFile, DossierImport

logger = logging.getLogger(__name__)

_MIME_EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}
_GENERIC_MIMES = {"", "application/octet-stream", "binary/octet-stream"}
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
_ENCODED_PATH = re.compile(r"%(?:2e|2f|5c|00|25)", re.I)
# Le Finder de macOS enregistre « / » sous la forme « : » (« FLUGEN 50MG/5ML » devient
# « FLUGEN 50MG:5ML ») : on accepte « : » au milieu d'un nom, sauf lettre de lecteur Windows
# (« C: ») et flux NTFS alternatif (« decision.pdf:script.exe »). Les fichiers sont de toute
# façon stockés sous un nom aléatoire : le chemin n'est qu'une métadonnée.
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
_ALTERNATE_STREAM = re.compile(r"\.[A-Za-z0-9]{1,5}:")
_FORBIDDEN_PDF_KEYS = {
    "/A", "/AA", "/OpenAction", "/JS", "/JavaScript", "/EmbeddedFiles",
    "/RichMediaContent", "/RichMediaSettings", "/XFA", "/EF",
}
_FORBIDDEN_PDF_TYPES = {"/EmbeddedFile", "/Filespec", "/Action", "/RichMedia"}


def _reject(message: str, field: str = "files") -> None:
    raise ValidationError({field: message})


def _validate_segment(segment: str) -> None:
    if (
        not segment
        or len(segment) > 255
        or segment in {".", ".."}
        or any(character in segment for character in ("/", "\\"))
        or _DRIVE_LETTER.match(segment)
        or _ALTERNATE_STREAM.search(segment)
        or any(unicodedata.category(character).startswith("C") for character in segment)
        or segment.endswith((".", " "))
        or _WINDOWS_RESERVED.match(segment)
        or _ENCODED_PATH.search(segment)
    ):
        _reject("Nom de fichier ou de dossier non autorisé.", "paths")


def validate_relative_path(path: str, root_name: str) -> str:
    """Reject ambiguous POSIX paths, including Windows and encoded traversal forms."""
    if not isinstance(root_name, str):
        _reject("Le nom du dossier est obligatoire.", "root_name")
    _validate_segment(root_name)
    if not isinstance(path, str) or len(path) > 500:
        _reject("Chemin relatif invalide ou trop long (500 caractères maximum).", "paths")
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != root_name:
        _reject("Tous les fichiers doivent appartenir au dossier sélectionné.", "paths")
    for segment in parts:
        _validate_segment(segment)
    return path


def _validate_pdf(content: bytes) -> None:
    """Inspect reachable objects without decoding document streams or executing actions."""
    try:
        # Lecture tolérante : les scanners produisent des PDF légèrement non conformes (clé
        # /Info en double dans le trailer, sur 20 des 44 décisions du Cameroun) que le mode
        # strict refusait. La sécurité ne repose pas sur ce mode mais sur le parcours ci-dessous,
        # qui refuse toute action active ou fichier incorporé.
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            _reject("Les PDF chiffrés ne sont pas acceptés.")
        stack = [(reader.trailer, 0)]
        seen_indirect: set[tuple[int, int]] = set()
        seen_direct: set[int] = set()
        visited = 0
        while stack:
            item, depth = stack.pop()
            visited += 1
            if visited > 100_000 or depth > 128 or len(stack) > 100_000:
                _reject("Structure PDF trop complexe pour être contrôlée en sécurité.")
            if isinstance(item, IndirectObject):
                identity = (item.idnum, item.generation)
                if identity in seen_indirect:
                    continue
                seen_indirect.add(identity)
                stack.append((item.get_object(), depth + 1))
            elif isinstance(item, DictionaryObject):
                if id(item) in seen_direct:
                    continue
                seen_direct.add(id(item))
                if (
                    _FORBIDDEN_PDF_KEYS.intersection(item.keys())
                    or str(item.get("/Type", "")) in _FORBIDDEN_PDF_TYPES
                    or str(item.get("/S", "")) in {
                        "/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR",
                    }
                ):
                    _reject("PDF refusé : actions actives ou fichiers incorporés détectés.")
                if len(item) + len(stack) > 100_000:
                    _reject("Structure PDF trop complexe.")
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, ArrayObject):
                if id(item) in seen_direct:
                    continue
                seen_direct.add(id(item))
                if len(item) + len(stack) > 100_000:
                    _reject("Structure PDF trop complexe.")
                stack.extend((child, depth + 1) for child in item)
        page_count = len(reader.pages)
        maximum = int(getattr(settings, "DOSSIER_MAX_PAGES", 100))
        if page_count < 1 or page_count > maximum:
            _reject(f"Le PDF doit contenir entre 1 et {maximum} pages.")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError({"files": "PDF illisible ou structure PDF invalide."}) from exc


def _validate_image(content: bytes, mime: str) -> None:
    expected = "JPEG" if mime == "image/jpeg" else "PNG"
    maximum = int(getattr(settings, "DOSSIER_MAX_IMAGE_PIXELS", 40_000_000))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format != expected:
                    _reject("Le format réel de l'image ne correspond pas à son extension.")
                if image.width < 1 or image.height < 1 or image.width * image.height > maximum:
                    _reject(f"Image trop grande ({maximum} pixels maximum).")
                if getattr(image, "n_frames", 1) != 1:
                    _reject("Les images animées ou contenant plusieurs images sont refusées.")
                image.verify()
            # verify() alone does not fully decode JPEGs; load() catches truncated scans.
            with Image.open(io.BytesIO(content)) as image:
                image.load()
    except ValidationError:
        raise
    except (
        UnidentifiedImageError, Image.DecompressionBombError,
        Image.DecompressionBombWarning, OSError, ValueError, SyntaxError,
    ) as exc:
        raise ValidationError({"files": "Image illisible, endommagée ou trop grande."}) from exc


def _antivirus(content: bytes, extension: str) -> None:
    configured = getattr(settings, "DOSSIER_CLAMAV_COMMAND", "")
    if not configured:
        if getattr(settings, "DOSSIER_REQUIRE_ANTIVIRUS", False):
            _reject("L'antivirus obligatoire n'est pas configuré. Import refusé.")
        return
    try:
        command = shlex.split(configured) if isinstance(configured, str) else list(configured)
        if not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError("Invalid scanner command")
        with tempfile.NamedTemporaryFile(suffix=extension) as source:
            source.write(content)
            source.flush()
            result = subprocess.run(
                [*command, "--", source.name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=int(getattr(settings, "DOSSIER_CLAMAV_TIMEOUT", 60)),
                check=False,
            )
        if result.returncode == 1:
            _reject("Fichier refusé par l'antivirus.")
        if result.returncode != 0:
            _reject("Le contrôle antivirus a échoué. Import refusé.")
    except ValidationError:
        raise
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        raise ValidationError({"files": "Antivirus indisponible. Import refusé."}) from exc


@dataclass
class _ValidatedUpload:
    path: str
    temporary: object
    sha256: str
    mime: str
    size: int


def _validate_content(upload, path: str, remaining: int) -> tuple[bytes, str]:
    original_name = getattr(upload, "name", "")
    if not isinstance(original_name, str):
        _reject("Nom de fichier invalide.")
    _validate_segment(original_name)
    maximum = int(getattr(settings, "DOCUMENT_MAX_MB", 25)) * 1024 * 1024
    declared = getattr(upload, "size", None)
    if declared is not None and (declared > maximum or declared > remaining):
        _reject("Fichier ou dossier trop volumineux.")
    upload.seek(0)
    content = upload.read(min(maximum, remaining) + 1)
    if not content:
        _reject("Les fichiers vides ne sont pas acceptés.")
    if len(content) > maximum or len(content) > remaining:
        _reject("Fichier ou dossier trop volumineux.")
    if content.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    else:
        _reject("Format non accepté : seuls PDF, JPEG et PNG sont autorisés.")
    extension = PurePosixPath(path).suffix.lower()
    upload_extension = PurePosixPath(original_name).suffix.lower()
    allowed = _MIME_EXTENSIONS[mime]
    if extension not in allowed or upload_extension not in allowed:
        _reject("L'extension du fichier ne correspond pas à son contenu réel.")
    declared_mime = (getattr(upload, "content_type", "") or "").split(";", 1)[0].lower().strip()
    if declared_mime not in _GENERIC_MIMES and declared_mime != mime:
        _reject("Le type MIME déclaré ne correspond pas au contenu réel du fichier.")
    _antivirus(content, extension)
    if mime == "application/pdf":
        _validate_pdf(content)
    else:
        _validate_image(content, mime)
    return content, mime


def stage_dossier(*, uploads: list, paths: list[str], root_name: str, user) -> DossierImport:
    """Validate the entire selection before writing records, then stage it atomically.

    File content is spooled to local temporary storage, so a large accepted folder is
    not kept entirely in RAM. Storage side effects are compensated on any write failure.
    Identical bytes at distinct paths are preserved for subsequent deduplication.
    """
    if not isinstance(uploads, list):
        _reject("La sélection doit être une liste de fichiers.")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        _reject("Les chemins doivent être une liste de chaînes de caractères.", "paths")
    maximum_files = int(getattr(settings, "DOSSIER_MAX_FILES", 200))
    if not uploads or len(uploads) > maximum_files:
        _reject(f"Sélectionnez entre 1 et {maximum_files} fichiers.")
    if len(paths) != len(uploads):
        _reject("Chaque fichier doit posséder un chemin relatif.", "paths")
    seen_paths = set()
    for path in paths:
        validate_relative_path(path, root_name)
        normalized = unicodedata.normalize("NFC", path).casefold()
        if normalized in seen_paths:
            _reject("Plusieurs fichiers utilisent le même chemin relatif.", "paths")
        seen_paths.add(normalized)

    validated: list[_ValidatedUpload] = []
    stored: list[tuple[object, str]] = []
    remaining = int(getattr(settings, "DOSSIER_MAX_MB", 250)) * 1024 * 1024
    try:
        for upload, path in zip(uploads, paths, strict=True):
            content, mime = _validate_content(upload, path, remaining)
            temporary = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
            try:
                temporary.write(content)
                temporary.seek(0)
            except Exception:
                temporary.close()
                raise
            validated.append(_ValidatedUpload(
                path=path, temporary=temporary, sha256=hashlib.sha256(content).hexdigest(),
                mime=mime, size=len(content),
            ))
            remaining -= len(content)
        with transaction.atomic():
            batch = DossierImport.objects.create(root_name=root_name, created_by=user)
            for item in validated:
                record = DossierFile(
                    batch=batch, relative_path=item.path, sha256=item.sha256,
                    content_type=item.mime, size_bytes=item.size,
                )
                storage = record.file.storage
                destination = record.file.field.generate_filename(
                    record, PurePosixPath(item.path).name,
                )
                # Register the intended key before save(), even if a backend writes
                # the object and then fails to return its response.
                stored.append((storage, destination))
                saved_name = storage.save(destination, File(item.temporary))
                if saved_name != destination:
                    stored.append((storage, saved_name))
                record.file.name = saved_name
                record.save()
        return batch
    except Exception:
        for storage, name in reversed(stored):
            try:
                storage.delete(name)
            except Exception:
                logger.exception("Échec de suppression d'un fichier d'import incomplet : %s", name)
        raise
    finally:
        for item in validated:
            item.temporary.close()
