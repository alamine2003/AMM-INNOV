"""Local document extraction. Uploaded content never leaves the application host."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

MAX_PAGES = 30
MAX_TEXT = 160_000
MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_PIXELS = 20_000_000
OCR_TIMEOUT = 25
MIN_PAGE_TEXT = 35


def _ocr_image(path: Path, workspace: Path, page: int) -> str:
    with Image.open(path) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Image trop grande pour l'OCR (20 mégapixels maximum).")
        image.verify()
    target = workspace / f"ocr-{page}"
    subprocess.run(
        ["tesseract", str(path), str(target), "-l", "fra+eng", "--psm", "3"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=OCR_TIMEOUT,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    with target.with_suffix(".txt").open(encoding="utf-8", errors="replace") as output:
        return output.read(MAX_TEXT + 1)


def extract_file(upload) -> dict:
    """Return JSON diagnostics, text and metadata; never mistake failed OCR for success."""
    result = {
        "text": "",
        "metadata": {},
        "source": "unreadable",
        "confidence": 0,
        "page_count": None,
        "warnings": [],
        "errors": [],
        "truncated": False,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="amm-extract-") as temporary:
            workspace = Path(temporary)
            is_pdf = upload.content_type == "application/pdf"
            source = workspace / ("source.pdf" if is_pdf else "source.image")
            total = 0
            with upload.file.open("rb") as stream, source.open("wb") as output:
                for chunk in stream.chunks():
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise ValueError("Fichier trop volumineux pour l'extraction.")
                    output.write(chunk)
            texts, used_ocr, sparse_pages = [], False, []
            if is_pdf:
                reader = PdfReader(source, strict=False)
                if reader.is_encrypted and not reader.decrypt(""):
                    raise ValueError("PDF chiffré : extraction impossible.")
                page_count = len(reader.pages)
                result["page_count"] = page_count
                result["truncated"] = page_count > MAX_PAGES
                metadata = reader.metadata or {}
                result["metadata"] = {
                    str(key).lstrip("/"): str(value)[:1000]
                    for key, value in metadata.items()
                    if str(key) in ("/Title", "/Subject", "/Author", "/CreationDate")
                }
                for index, page in enumerate(reader.pages[:MAX_PAGES]):
                    try:
                        page_text = (page.extract_text() or "")[: MAX_TEXT + 1]
                    except Exception:
                        page_text = ""
                        result["warnings"].append(f"Texte PDF illisible à la page {index + 1}.")
                    texts.append(page_text)
                    if len("".join(page_text.split())) < MIN_PAGE_TEXT:
                        sparse_pages.append(index)
                    if sum(map(len, texts)) > MAX_TEXT:
                        result["truncated"] = True
                        break
            else:
                result["page_count"] = 1
                texts, sparse_pages = [""], [0]
            if sparse_pages:
                required = ["tesseract"] + (["pdftoppm"] if is_pdf else [])
                missing = [binary for binary in required if not shutil.which(binary)]
                if missing:
                    result["errors"].append("OCR indisponible : " + ", ".join(missing) + ".")
                else:
                    for index in sparse_pages:
                        try:
                            image_path = source
                            if is_pdf:
                                prefix = workspace / f"page-{index + 1}"
                                subprocess.run(
                                    [
                                        "pdftoppm",
                                        "-f",
                                        str(index + 1),
                                        "-l",
                                        str(index + 1),
                                        "-singlefile",
                                        "-scale-to",
                                        "2200",
                                        "-png",
                                        str(source),
                                        str(prefix),
                                    ],
                                    check=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=OCR_TIMEOUT,
                                )
                                image_path = prefix.with_suffix(".png")
                            ocr_text = _ocr_image(image_path, workspace, index)
                            if len(ocr_text.strip()) > len(texts[index].strip()):
                                texts[index] = ocr_text
                                used_ocr = True
                        except subprocess.TimeoutExpired:
                            result["errors"].append(f"Délai OCR dépassé à la page {index + 1}.")
                        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                            result["errors"].append(
                                f"Échec OCR à la page {index + 1} ({type(exc).__name__})."
                            )
            joined = "\n\n".join(texts)
            result["truncated"] = result["truncated"] or len(joined) > MAX_TEXT
            result["text"] = joined[:MAX_TEXT]
            if result["text"].strip():
                result["source"] = "ocr" if used_ocr else "pdf_text"
                result["confidence"] = 80 if used_ocr else 98
            else:
                result["errors"].append("Aucun texte exploitable dans le document.")
            if result["truncated"]:
                result["warnings"].append("Extraction limitée à 30 pages et 160 000 caractères.")
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        result["errors"].append(f"Extraction impossible : {message[:200]}.")
    return result
