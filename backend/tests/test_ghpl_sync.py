"""Synchronisation horaire avec le classement AMM GHPL (Nextcloud simulé, lecture seule)."""

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Product
from apps.documents.models import Document
from apps.imports.ghpl.source import manifest_rows
from apps.imports.ghpl.sync import run_sync
from apps.imports.ghpl.webdav import RemoteFile, TooLarge
from apps.imports.models import GhplSyncedFile, GhplSyncRun, ImportRow
from tests.conftest import MINIMAL_PDF

pytestmark = pytest.mark.django_db

REGISTRY = "0_REGISTRE AMM GHPL.xlsx"
CONSOLIDATION = [
    "Pays", "Gamme", "Produit", "Presentation", "Source", "Controle", "Statut dossier",
    "Referentiel", "N° AMM origine", "Date origine",
]  # fmt: skip
DOCS = [
    "Pays", "Gamme", "Produit", "Presentation", "Type", "Rangement", "Date", "Fiabilite date",
    "N° AMM", "Chemin", "Nom du fichier",
]  # fmt: skip
PRODUCT = "LOLIP 10MG CPR B30"
BASE = f"1_GAMME GENERALE/SENEGAL/LOLIP/{PRODUCT}"


def doc(kind, rangement, when, name, numero="", fiabilite="haute"):
    return {
        "Pays": "SENEGAL",
        "Gamme": "GAMME GENERALE",
        "Produit": "LOLIP",
        "Presentation": PRODUCT,
        "Type": kind,
        "Rangement": rangement,
        "Date": datetime.combine(when, datetime.min.time()) if when else None,
        "Fiabilite date": fiabilite,
        "N° AMM": numero,
        "Chemin": f"{BASE}/{rangement.replace(' > ', '/')}/{name}",
        "Nom du fichier": name,
    }


ORIGIN = doc(
    "AMM (octroi)",
    "1_AMM ORIGINE - 2019 - N° 885",
    date(2019, 7, 4),
    "2019-07-04 - AMM ORIGINE - LOLIP - SN.pdf",
    numero="885",
)
RENEWAL = doc(
    "Renouvellement",
    "2_RENOUVELLEMENTS > RENOUVELLEMENT 1 - 2024-07-10",
    date(2024, 7, 10),
    "2024-07-10 - RENOUVELLEMENT 1 - LOLIP - SN.pdf",
    numero="885/R1",
)


def workbook(docs, records=None) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "_Consolidation"
    sheet.append(CONSOLIDATION)
    for record in records or [
        {
            "Pays": "SENEGAL",
            "Gamme": "GAMME GENERALE",
            "Presentation": PRODUCT,
            "Source": "Classement seul",
            "Controle": "Classement seul",
            "Referentiel": PRODUCT,
            "N° AMM origine": "885",
            "Date origine": datetime(2019, 7, 4),
        }
    ]:
        sheet.append([record.get(column) for column in CONSOLIDATION])
    other = book.create_sheet("_Docs")
    other.append(DOCS)
    for values in docs:
        other.append([values.get(column) for column in DOCS])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class FakeNextcloud:
    """Le classement vu par WebDAV : un dictionnaire chemin → contenu, rien n'y est écrit."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.version = 0
        self.downloads: list[str] = []

    def publish(self, docs, records=None, files=None):
        self.version += 1
        self.files[REGISTRY] = workbook(docs, records)
        for values in docs:
            self.files.setdefault(values["Chemin"], MINIMAL_PDF + values["Chemin"].encode())
        self.files.update(files or {})

    def stat(self, path):
        if path not in self.files:
            return None
        return RemoteFile(path, f"v{self.version}", len(self.files[path]), None)

    def download(self, path, max_bytes):
        self.downloads.append(path)
        content = self.files.get(path)
        if content is not None and len(content) > max_bytes:
            raise TooLarge(f"{len(content) >> 20} Mo")
        return content


@pytest.fixture
def cloud(countries, ranges):
    return FakeNextcloud()


def amm_of_product():
    return MarketingAuthorization.objects.get(product__name=PRODUCT, country__iso2="SN")


def test_manifest_rows_follow_the_classement_rules():
    copy = doc("AMM (octroi)", "1_AMM ORIGINE - 2019 - N° 885 > _DOUBLONS (autres scans)",
               date(2019, 7, 4), "copie.pdf")  # fmt: skip
    year_only = dict(ORIGIN, Date=datetime(1905, 7, 18), Chemin="x/annee.pdf")
    rows = manifest_rows([ORIGIN, RENEWAL, copy, year_only], [])
    assert [(r["periode"], r["kind"], r["principal"]) for r in rows[:3]] == [
        ("ORIGINE", "AMM", "oui"),
        ("RENOUVELLEMENT 1", "AMM", "oui"),
        ("ORIGINE", "AMM", "non"),
    ]
    assert rows[0]["iso2"] == "SN" and rows[0]["date"] == "2019-07-04"
    assert rows[3]["date"] == "2026"  # année seule mise en forme de date dans Excel


def test_not_configured_does_nothing(settings):
    settings.NEXTCLOUD_USER = ""
    run = run_sync()
    assert run.status == GhplSyncRun.Status.NOT_CONFIGURED
    assert "NEXTCLOUD_USER" in run.message


def test_first_pass_creates_and_files_then_nothing_to_do(cloud):
    cloud.publish([ORIGIN, RENEWAL])
    run = run_sync(client=cloud)
    assert run.status == GhplSyncRun.Status.DONE, run.message
    amm = amm_of_product()
    assert amm.original_start_date == date(2019, 7, 4) and amm.original_number == "885"
    renewal = Renewal.objects.get(amm=amm)
    assert renewal.start_date == date(2024, 7, 10)
    docs = Document.objects.current().filter(amm=amm)
    assert docs.count() == 2
    assert docs.get(renewal=renewal).kind == "AMM"
    assert run.summary["downloaded"] == 2
    assert run.scans_batch.summary["source"] == "synchro"
    # Registre inchangé : rien n'est relu ni réimporté.
    again = run_sync(client=cloud)
    assert again.status == GhplSyncRun.Status.UP_TO_DATE
    assert len(cloud.downloads) == 3  # le registre + deux pièces, une seule fois
    # Registre réécrit sans changement réel (journal, « situation au ») : rien n'est réimporté.
    cloud.publish([ORIGIN, RENEWAL])
    third = run_sync(client=cloud)
    assert third.status == GhplSyncRun.Status.DONE
    assert third.scans_batch is None and third.registry_batch is None


def test_document_already_sent_is_attached_without_download(cloud, make_amm):
    amm = make_amm(
        "SN",
        product_obj=Product.objects.create(name=PRODUCT),
        original_number="885",
        original_start_date=date(2019, 7, 4),
    )
    from django.core.files.base import ContentFile

    from apps.documents.services.ingest import ingest_document

    sent = ingest_document(
        amm,
        ContentFile(MINIMAL_PDF + b"mac", name="x.pdf"),
        "AMM",
        document_date=date(2019, 7, 4),
        title=ORIGIN["Nom du fichier"],
    )
    cloud.publish([ORIGIN])
    run = run_sync(client=cloud)
    assert run.summary["adopted"] == 1 and not run.summary.get("downloaded")
    assert cloud.downloads == [REGISTRY]
    assert GhplSyncedFile.objects.get(path=ORIGIN["Chemin"]).document == sent


def test_reclassified_scan_follows_without_duplicate(cloud):
    misfiled = doc(
        "AMM (octroi)",
        "1_AMM ORIGINE - 2019 - N° 885",
        date(2024, 7, 10),
        "2024-07-10 - AMM ORIGINE - LOLIP - SN.pdf",
        fiabilite="moyenne",
    )
    cloud.publish([ORIGIN, RENEWAL, misfiled])
    run_sync(client=cloud)
    document = GhplSyncedFile.objects.get(path=misfiled["Chemin"]).document
    assert document.renewal is None
    # La tâche du classement range la décision dans le renouvellement (nouveau chemin et nom).
    moved = doc(
        "Renouvellement",
        "2_RENOUVELLEMENTS > RENOUVELLEMENT 1 - 2024-07-10",
        date(2024, 7, 10),
        "2024-07-10 - RENOUVELLEMENT 1 - LOLIP - SN (2).pdf",
    )
    cloud.files[moved["Chemin"]] = cloud.files[misfiled["Chemin"]]
    del cloud.files[misfiled["Chemin"]]
    cloud.publish([ORIGIN, RENEWAL, moved])
    run = run_sync(client=cloud)
    assert run.status == GhplSyncRun.Status.DONE, run.message
    document.refresh_from_db()
    assert document.renewal is not None and document.renewal.start_date == date(2024, 7, 10)
    assert Document.objects.current().filter(amm=document.amm).count() == 3
    assert run.summary["moved"] == 1
    old = GhplSyncedFile.objects.get(path=misfiled["Chemin"])
    assert old.state == GhplSyncedFile.State.REMOVED and old.message == "déplacé dans le classement"


def test_date_corrected_in_amm_gh_is_not_rewritten(cloud):
    cloud.publish([ORIGIN])
    run_sync(client=cloud)
    amm = amm_of_product()
    amm.original_start_date = date(2019, 7, 14)  # corrigée à la main dans AMM GH
    amm.save()
    # Le classement change pour cette présentation (nouvelle pièce) : la fiche reste corrigée.
    cloud.publish([ORIGIN, RENEWAL])
    run = run_sync(client=cloud)
    amm.refresh_from_db()
    assert amm.original_start_date == date(2019, 7, 14)
    warning = ImportRow.objects.filter(batch=run.scans_batch, outcome="WARNING").first()
    assert warning is not None and "fiche conservée" in warning.message


def test_truncated_registry_is_not_applied(cloud):
    others = [
        doc("Variation / rectificatif", "7_VARIATIONS - RECTIFICATIFS", date(2020, 1, n),
            f"variation {n}.pdf")
        for n in range(1, 11)
    ]  # fmt: skip
    cloud.publish([ORIGIN, RENEWAL, *others])
    run_sync(client=cloud)
    cloud.publish([ORIGIN])
    run = run_sync(client=cloud)
    assert run.status == GhplSyncRun.Status.FAILED
    assert "Registre incomplet" in run.message
    assert GhplSyncedFile.objects.filter(state=GhplSyncedFile.State.REMOVED).count() == 0


def test_word_and_oversized_files_are_listed_not_sent(cloud, settings):
    settings.DOCUMENT_MAX_MB = 1
    word = doc("Autre", "6_DEPOTS - COURRIERS", date(2025, 1, 2), "lettre.docx")
    big = doc("Variation / rectificatif", "7_VARIATIONS - RECTIFICATIFS", date(2021, 3, 2),
              "gros.pdf")  # fmt: skip
    cloud.publish([ORIGIN, word, big], files={big["Chemin"]: MINIMAL_PDF + b"0" * (2 << 20)})
    run = run_sync(client=cloud)
    assert run.status == GhplSyncRun.Status.DONE
    states = dict(GhplSyncedFile.objects.values_list("path", "state"))
    assert states[word["Chemin"]] == states[big["Chemin"]] == GhplSyncedFile.State.SKIPPED
    messages = {issue["message"] for issue in run.summary["issues"]}
    assert any("Word" in m for m in messages) and any("trop volumineux" in m for m in messages)


def test_status_api_for_headquarters_only(hq_client, country_client, settings):
    settings.NEXTCLOUD_USER = ""
    assert country_client.get("/api/v1/ghpl-sync").status_code == 403
    assert hq_client.post("/api/v1/ghpl-sync/run").status_code == 202
    body = hq_client.get("/api/v1/ghpl-sync").json()
    assert body["configured"] is False
    assert body["last_run"]["status"] == "NOT_CONFIGURED"
    assert hq_client.get("/api/v1/ghpl-sync/files?state=SKIPPED").json()["count"] == 0


def test_late_sync_is_caught_up_after_waking(settings, monkeypatch):
    from django.utils import timezone

    from apps.core.tasks import recover_ghpl_sync
    from apps.imports import tasks

    calls = []
    monkeypatch.setattr(tasks.sync_ghpl, "delay", lambda *a, **k: calls.append(a))
    settings.NEXTCLOUD_USER, settings.NEXTCLOUD_APP_PASSWORD = "", ""
    assert recover_ghpl_sync(timezone.now()) == 0  # non configurée : rien
    settings.NEXTCLOUD_USER, settings.NEXTCLOUD_APP_PASSWORD = "siege", "secret"
    assert recover_ghpl_sync(timezone.now()) == 1 and len(calls) == 1
    GhplSyncRun.objects.create(status=GhplSyncRun.Status.UP_TO_DATE)
    assert recover_ghpl_sync(timezone.now()) == 0  # passage récent : on attend l'heure


def test_webdav_url_quotes_every_segment():
    from apps.imports.ghpl.webdav import Nextcloud

    client = Nextcloud("https://cloud.test/", "m.gueye", "x", "AMM GHPL - CLASSEMENT GENERAL")
    assert client.url("1_GAMME/N° 885/a b.pdf") == (
        "https://cloud.test/remote.php/dav/files/m.gueye/"
        "AMM%20GHPL%20-%20CLASSEMENT%20GENERAL/1_GAMME/N%C2%B0%20885/a%20b.pdf"
    )


def test_webdav_reads_version_and_refuses_bad_credentials(monkeypatch):
    import urllib.error

    from apps.imports.ghpl import webdav

    body = (
        b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response>'
        b"<d:href>/remote.php/dav/files/u/r.xlsx</d:href><d:propstat><d:prop>"
        b'<d:getetag>"abc123"</d:getetag><d:getcontentlength>2502899</d:getcontentlength>'
        b"<d:getlastmodified>Wed, 22 Oct 2026 12:41:00 GMT</d:getlastmodified>"
        b"</d:prop></d:propstat></d:response></d:multistatus>"
    )
    seen = []

    class Response(BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        seen.append((request.get_method(), request.get_header("Depth")))
        if "refus" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)
        return Response(body)

    monkeypatch.setattr(webdav.urllib.request, "urlopen", urlopen)
    client = webdav.Nextcloud("https://cloud.test", "u", "x", "racine")
    remote = client.stat("r.xlsx")
    assert (remote.etag, remote.size, remote.modified.year) == ("abc123", 2502899, 2026)
    assert seen == [("PROPFIND", "0")]  # lecture seule, profondeur 0
    with pytest.raises(webdav.NextcloudError, match="mot de passe d'application"):
        client.stat("refus.xlsx")


SIBLING = "LOLIP 20MG CPR B30"


def grouped(presentation, name):
    values = doc(
        "AMM (octroi)",
        "1_AMM ORIGINE - 2019 - N° 885",
        date(2019, 7, 4),
        name,
        numero="885",
    )
    values["Presentation"] = presentation
    values["Chemin"] = f"1_GAMME GENERALE/SENEGAL/LOLIP/{presentation}/1_AMM ORIGINE/{name}"
    return values


def sibling_records():
    return [
        {
            "Pays": "SENEGAL",
            "Gamme": "GAMME GENERALE",
            "Presentation": name,
            "Source": "Classement seul",
            "Controle": "Classement seul",
            "Referentiel": name,
            "N° AMM origine": "885",
            "Date origine": datetime(2019, 7, 4),
        }
        for name in (PRODUCT, SIBLING)
    ]


def test_grouped_decision_gets_a_copy_on_each_record(cloud):
    first = grouped(PRODUCT, "decision groupee.pdf")
    second = grouped(SIBLING, "decision groupee (2).pdf")
    shared = MINIMAL_PDF + b"decision groupee"
    cloud.publish(
        [first, second],
        records=sibling_records(),
        files={first["Chemin"]: shared, second["Chemin"]: shared},
    )
    run = run_sync(client=cloud)
    assert run.status == GhplSyncRun.Status.DONE, run.message
    for name in (PRODUCT, SIBLING):
        amm = MarketingAuthorization.objects.get(product__name=name)
        assert Document.objects.current().filter(amm=amm).count() == 1, name
    assert not run.summary.get("moved")


def test_scan_taken_from_a_sibling_record_is_given_back(cloud):
    first = grouped(PRODUCT, "decision groupee.pdf")
    second = grouped(SIBLING, "decision groupee (2).pdf")
    shared = MINIMAL_PDF + b"decision groupee"
    cloud.publish(
        [first, second],
        records=sibling_records(),
        files={first["Chemin"]: shared, second["Chemin"]: shared},
    )
    run_sync(client=cloud)
    # État laissé par la 1.1.0 : la copie de la première fiche a été déplacée sur la seconde.
    mine = GhplSyncedFile.objects.get(path=first["Chemin"])
    theirs = GhplSyncedFile.objects.get(path=second["Chemin"])
    Document.objects.filter(pk=theirs.document_id).delete()
    Document.objects.filter(pk=mine.document_id).update(amm=theirs.amm_id)
    theirs.document_id = mine.document_id
    theirs.save()
    run = run_sync(client=cloud)  # registre inchangé : la réparation passe quand même
    assert run.summary["repaired"] == 1
    for name in (PRODUCT, SIBLING):
        amm = MarketingAuthorization.objects.get(product__name=name)
        assert Document.objects.current().filter(amm=amm).count() == 1, name
