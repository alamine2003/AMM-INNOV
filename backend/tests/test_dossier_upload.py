"""Folder intake rejects spoofing before writes and compensates storage failures."""

import hashlib
import io
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from apps.imports.dossier import upload as upload_service
from apps.imports.dossier.upload import stage_dossier, validate_relative_path
from apps.imports.models import DossierFile, DossierImport

pytestmark = pytest.mark.django_db


def pdf_bytes(*, pages=1, active=None, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if active == "javascript":
        writer.add_js("app.alert('test');")
    elif active == "attachment":
        writer.add_attachment("payload.txt", b"content")
    elif active == "launch":
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject({
            NameObject("/S"): NameObject("/Launch"),
            NameObject("/F"): TextStringObject("application.exe"),
        })
    elif active == "nested":
        writer._root_object[NameObject("/Unusual")] = ArrayObject([
            DictionaryObject({NameObject("/AA"): DictionaryObject()})
        ])
    elif active == "too_deep":
        nested = DictionaryObject()
        writer._root_object[NameObject("/Unusual")] = nested
        for _ in range(140):
            child = DictionaryObject()
            nested[NameObject("/Next")] = child
            nested = child
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_bytes(format="PNG", size=(8, 8)):
    output = io.BytesIO()
    Image.new("RGB", size, "white").save(output, format=format)
    return output.getvalue()


def uploaded(content=None, name="decision.pdf", mime="application/pdf"):
    return SimpleUploadedFile(name, pdf_bytes() if content is None else content, content_type=mime)


@pytest.fixture(autouse=True)
def isolated_storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.DOSSIER_CLAMAV_COMMAND = ""
    settings.DOSSIER_REQUIRE_ANTIVIRUS = False
    return tmp_path / "media"


@pytest.mark.parametrize("path", [
    "../Dossier/decision.pdf", "/Dossier/decision.pdf", "Dossier/../decision.pdf",
    "Dossier/./decision.pdf", "Dossier//decision.pdf", "Dossier/decision.pdf/",
    "Dossier\\decision.pdf", "Dossier/AMM\\decision.pdf", "Dossier/C:/decision.pdf",
    "Dossier/file.pdf:script.exe", "Dossier/\x00decision.pdf", "Dossier/\ndecision.pdf",
    "Dossier/\u202edecision.pdf", "Dossier/CON.pdf", "Dossier/aux/decision.pdf",
    "Dossier/LPT1.pdf", "Dossier/decision.pdf.", "Dossier/decision.pdf ",
    "Dossier/%2e%2e/decision.pdf", "Dossier/%252e%252e/decision.pdf",
    "Dossier/%2fetc/decision.pdf", "Another/decision.pdf", "Dossier",
    f"Dossier/{'x' * 256}.pdf", f"Dossier/{'x' * 250}/{'x' * 250}.pdf",
])
def test_unsafe_relative_paths_rejected(path):
    with pytest.raises(ValidationError):
        validate_relative_path(path, "Dossier")


@pytest.mark.parametrize("path", [
    # Noms réels du dossier Cameroun : le Finder de macOS écrit « / » sous la forme « : ».
    "CAMEROUN/FLUGEN 50MG :5ML PDRE SUSP BUV F60ML/AMM renouvellée FLUGEN SYROP.pdf",
    "CAMEROUN/GENSET 10MG CPR B3:0/AMM GENSET CP B30_EXP.2028.pdf",
    "CAMEROUN/LITACOLD NUIT 500MG:25MG CPR B16/AMM LITACOLD NUIT_2028.pdf",
    "CAMEROUN/PANTOPRAL D 40MG30MG CPR B30/AMM PANTOPRAL D _2028.pdf",
])
def test_macos_colons_in_names_are_accepted(path):
    assert validate_relative_path(path, "CAMEROUN") == path


@pytest.mark.parametrize("root", ["", ".", "..", "../Dossier", "a/b", "C:\\Dossier", "x" * 256])
def test_unsafe_roots_rejected(root):
    with pytest.raises(ValidationError):
        validate_relative_path(f"{root}/decision.pdf", root)


@pytest.mark.parametrize("paths", [None, 1, True, "Dossier/decision.pdf", {}, [None], [1]])
def test_paths_must_be_a_list_of_strings(users, paths):
    with pytest.raises(ValidationError, match="liste de chaînes"):
        stage_dossier(uploads=[uploaded()], paths=paths, root_name="Dossier", user=users["hq"])


@pytest.mark.parametrize("uploads", [None, 1, "decision.pdf", {}, ()])
def test_uploads_must_be_a_list(users, uploads):
    with pytest.raises(ValidationError, match="liste de fichiers"):
        stage_dossier(
            uploads=uploads, paths=["Dossier/decision.pdf"], root_name="Dossier", user=users["hq"],
        )


def test_preserves_structure_original_content_and_hash(users):
    original = pdf_bytes()
    batch = stage_dossier(
        uploads=[uploaded(original)], paths=["Dossier/AMM_ORIGINE/décision.pdf"],
        root_name="Dossier", user=users["hq"],
    )
    file = batch.files.get()
    assert batch.created_by == users["hq"]
    assert batch.status == DossierImport.Status.PENDING
    assert file.relative_path == "Dossier/AMM_ORIGINE/décision.pdf"
    assert file.sha256 == hashlib.sha256(original).hexdigest()
    assert file.size_bytes == len(original)
    assert file.content_type == "application/pdf"
    assert file.file.name.startswith(f"imports/dossiers/{batch.pk}/")
    assert "décision" not in file.file.name
    with file.file.open("rb") as stored:
        assert stored.read() == original


@pytest.mark.parametrize(("format", "name", "mime"), [
    ("PNG", "scan.png", "image/png"), ("JPEG", "scan.jpeg", "image/jpeg"),
])
def test_original_images_not_converted(users, format, name, mime):
    original = image_bytes(format)
    batch = stage_dossier(
        uploads=[uploaded(original, name, mime)], paths=[f"Dossier/{name}"],
        root_name="Dossier", user=users["hq"],
    )
    file = batch.files.get()
    assert file.content_type == mime
    with file.file.open("rb") as stored:
        assert stored.read() == original


@pytest.mark.parametrize(("name", "path", "mime", "content"), [
    ("decision.png", "Dossier/decision.png", "image/png", pdf_bytes()),
    ("decision.pdf", "Dossier/decision.pdf", "image/png", pdf_bytes()),
    ("decision.exe", "Dossier/decision.pdf", "application/pdf", pdf_bytes()),
    ("decision.pdf", "Dossier/decision.exe", "application/pdf", pdf_bytes()),
    ("decision.pdf", "Dossier/decision.pdf", "application/pdf", b"%PDF-not-real"),
    ("decision.pdf", "Dossier/decision.pdf", "application/pdf", b"MZpayload"),
    ("decision.pdf", "Dossier/decision.pdf", "application/pdf", b""),
    ("scan.png", "Dossier/scan.png", "image/png", b"\x89PNG\r\n\x1a\ninvalid"),
    ("scan.jpg", "Dossier/scan.jpg", "image/jpeg", b"\xff\xd8\xffinvalid"),
])
def test_mime_extension_spoofing_and_malformed_files_rejected(
    users, isolated_storage, name, path, mime, content,
):
    with pytest.raises(ValidationError):
        stage_dossier(
            uploads=[uploaded(content, name, mime)], paths=[path],
            root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()
    assert not DossierFile.objects.exists()
    assert not isolated_storage.exists()


@pytest.mark.parametrize("mime", ["application/octet-stream", "", None])
def test_generic_mime_accepted_after_signature_validation(users, mime):
    batch = stage_dossier(
        uploads=[uploaded(mime=mime)], paths=["Dossier/decision.pdf"],
        root_name="Dossier", user=users["hq"],
    )
    assert batch.files.get().content_type == "application/pdf"


@pytest.mark.parametrize("second", ["decision.pdf", "DECISION.pdf"])
def test_duplicate_paths_rejected(users, second):
    with pytest.raises(ValidationError, match="même chemin"):
        stage_dossier(
            uploads=[uploaded(), uploaded(name=second)],
            paths=["Dossier/decision.pdf", f"Dossier/{second}"],
            root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()


def test_same_bytes_at_distinct_paths_staged_for_later_deduplication(users):
    original = pdf_bytes()
    batch = stage_dossier(
        uploads=[uploaded(original), uploaded(original)],
        paths=["Dossier/AMM/decision.pdf", "Dossier/ARCHIVES/decision.pdf"],
        root_name="Dossier", user=users["hq"],
    )
    assert batch.files.count() == 2
    assert batch.files.values("sha256").distinct().count() == 1
    assert batch.files.values("file").distinct().count() == 2


@pytest.mark.parametrize("active", ["javascript", "attachment", "launch", "nested", "too_deep"])
def test_pdf_active_content_and_unbounded_structures_rejected(users, active):
    with pytest.raises(ValidationError):
        stage_dossier(
            uploads=[uploaded(pdf_bytes(active=active))], paths=["Dossier/decision.pdf"],
            root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()


def test_encrypted_pdf_rejected(users):
    with pytest.raises(ValidationError, match="chiffrés"):
        stage_dossier(
            uploads=[uploaded(pdf_bytes(encrypted=True))], paths=["Dossier/decision.pdf"],
            root_name="Dossier", user=users["hq"],
        )


def test_file_page_pixel_and_folder_limits(users, settings):
    args = {"root_name": "Dossier", "user": users["hq"]}
    settings.DOSSIER_MAX_FILES = 1
    with pytest.raises(ValidationError):
        stage_dossier(
            uploads=[uploaded(), uploaded()], paths=["Dossier/1.pdf", "Dossier/2.pdf"], **args,
        )
    settings.DOSSIER_MAX_PAGES = 1
    with pytest.raises(ValidationError, match="pages"):
        stage_dossier(uploads=[uploaded(pdf_bytes(pages=2))], paths=["Dossier/1.pdf"], **args)
    settings.DOSSIER_MAX_IMAGE_PIXELS = 10
    with pytest.raises(ValidationError, match="pixels"):
        stage_dossier(
            uploads=[uploaded(image_bytes(), "scan.png", "image/png")],
            paths=["Dossier/scan.png"], **args,
        )
    settings.DOCUMENT_MAX_MB = 1
    with pytest.raises(ValidationError, match="volumineux"):
        stage_dossier(uploads=[uploaded(b"x" * (1024 * 1024 + 1))], paths=["Dossier/1.pdf"], **args)
    settings.DOSSIER_MAX_MB = 0
    with pytest.raises(ValidationError, match="volumineux"):
        stage_dossier(uploads=[uploaded()], paths=["Dossier/1.pdf"], **args)


def test_untrusted_declared_size_cannot_bypass_actual_limit(users, settings):
    settings.DOCUMENT_MAX_MB = 1
    source = uploaded(b"x" * (1024 * 1024 + 1))
    source.size = 1
    with pytest.raises(ValidationError, match="volumineux"):
        stage_dossier(
            uploads=[source], paths=["Dossier/decision.pdf"], root_name="Dossier", user=users["hq"],
        )


def test_no_storage_writes_if_later_file_invalid(users, isolated_storage):
    with pytest.raises(ValidationError):
        stage_dossier(
            uploads=[uploaded(), uploaded(b"invalid")],
            paths=["Dossier/1.pdf", "Dossier/2.pdf"], root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()
    assert not isolated_storage.exists()


def test_database_failure_cleans_up_all_storage_writes(users, isolated_storage, monkeypatch):
    original_save = DossierFile.save
    saved = []

    def fail_second(record, *args, **kwargs):
        saved.append(record.pk)
        if len(saved) == 2:
            raise RuntimeError("Database unavailable")
        return original_save(record, *args, **kwargs)

    monkeypatch.setattr(DossierFile, "save", fail_second)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        stage_dossier(
            uploads=[uploaded(), uploaded()], paths=["Dossier/1.pdf", "Dossier/2.pdf"],
            root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()
    assert not DossierFile.objects.exists()
    assert not [path for path in isolated_storage.rglob("*") if path.is_file()]


def test_storage_failure_after_write_cleans_up_partial_object(users, isolated_storage, monkeypatch):
    storage = DossierFile._meta.get_field("file").storage
    original_save = storage.save

    def interrupted(name, content, **kwargs):
        original_save(name, content, **kwargs)
        raise OSError("Storage response lost")

    monkeypatch.setattr(storage, "save", interrupted)
    with pytest.raises(OSError, match="Storage response lost"):
        stage_dossier(
            uploads=[uploaded()], paths=["Dossier/1.pdf"], root_name="Dossier", user=users["hq"],
        )
    assert not DossierImport.objects.exists()
    assert not [path for path in isolated_storage.rglob("*") if path.is_file()]


def test_required_antivirus_fails_closed(users, settings):
    settings.DOSSIER_REQUIRE_ANTIVIRUS = True
    with pytest.raises(ValidationError, match="antivirus obligatoire"):
        stage_dossier(
            uploads=[uploaded()], paths=["Dossier/1.pdf"], root_name="Dossier", user=users["hq"],
        )


@pytest.mark.parametrize("returncode", [1, 2])
def test_antivirus_refusal_or_scanner_error_rejects_upload(
    users, settings, monkeypatch, returncode,
):
    settings.DOSSIER_CLAMAV_COMMAND = "clamdscan --no-summary"
    calls = []

    def scanner(command, **kwargs):
        calls.append((command, kwargs))
        assert command[:3] == ["clamdscan", "--no-summary", "--"]
        assert command[-1].endswith(".pdf")
        assert kwargs["timeout"] == 60
        assert "shell" not in kwargs
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(upload_service.subprocess, "run", scanner)
    with pytest.raises(ValidationError, match="antivirus"):
        stage_dossier(
            uploads=[uploaded()], paths=["Dossier/1.pdf"], root_name="Dossier", user=users["hq"],
        )
    assert len(calls) == 1
    assert not DossierImport.objects.exists()


def test_scanner_timeout_rejects_upload(users, settings, monkeypatch):
    settings.DOSSIER_CLAMAV_COMMAND = ["clamdscan"]

    def timeout(command, **kwargs):
        raise upload_service.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(upload_service.subprocess, "run", timeout)
    with pytest.raises(ValidationError, match="indisponible"):
        stage_dossier(
            uploads=[uploaded()], paths=["Dossier/1.pdf"], root_name="Dossier", user=users["hq"],
        )
