"""Classeur complet avec les décisions officielles : chaque fiche est suivie de ses scans.

Assemblé en arrière-plan (tâche Celery) puis rangé dans le stockage des documents. Le service
tourne dans 512 Mo avec le worker : les scans sont copiés sur disque un par un, puis le PDF
est assemblé par qpdf, qui ne lit chaque scan qu'au moment d'écrire : jamais tout un classeur
en mémoire.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import img2pdf
from django.core.files import File
from django.db.models import F
from django.utils import timezone
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from apps.documents.models import Document

from .layout import binder_by_key, binder_detail
from .models import BinderExport
from .pdf import BinderDocument

logger = logging.getLogger(__name__)

KEEP = 1  # exports conservés par classeur (le plus récent)


def decisions_by_amm(amm_ids) -> dict[str, list[Document]]:
    """Décisions officielles en vigueur : l'origine d'abord, puis les renouvellements."""
    documents = (
        Document.objects.current()
        .filter(amm_id__in=amm_ids, kind=Document.Kind.AMM)
        .select_related("renewal")
        .order_by()
    )
    grouped: dict[str, list[Document]] = {}
    for document in documents:
        grouped.setdefault(str(document.amm_id), []).append(document)
    for items in grouped.values():
        items.sort(
            key=lambda d: (
                d.renewal.sequence if d.renewal_id else 0,
                d.document_date,
                d.uploaded_at,
            )
        )
    return grouped


def _placeholder(path: Path, document: Document, reason: str) -> None:
    """Page de remplacement quand un scan ne peut pas être joint."""
    canvas = Canvas(str(path), pagesize=A4)
    width, height = A4
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawCentredString(width / 2, height / 2 + 20, "Décision officielle non jointe")
    canvas.setFont("Helvetica", 11)
    canvas.drawCentredString(
        width / 2,
        height / 2 - 6,
        f"{document.amm.product.name} — scan du {document.document_date:%d/%m/%Y}",
    )
    canvas.drawCentredString(width / 2, height / 2 - 26, reason)
    canvas.showPage()
    canvas.save()


def _to_pdf(document: Document, workdir: Path) -> Path:
    """Copie le scan sur disque (PDF tel quel, image convertie) et renvoie son chemin."""
    raw = workdir / f"{document.pk}.src"
    document.file.open("rb")
    try:
        with raw.open("wb") as out:
            shutil.copyfileobj(document.file, out, length=1024 * 1024)
    finally:
        document.file.close()
    if document.content_type == "application/pdf":
        return raw
    target = workdir / f"{document.pk}.pdf"
    try:
        target.write_bytes(img2pdf.convert(str(raw)))
    except Exception:
        # Image avec transparence ou format exotique : conversion par Pillow.
        with Image.open(raw) as image:
            image.convert("RGB").save(target, "PDF", resolution=150)
    raw.unlink(missing_ok=True)
    return target


def _progress(export: BinderExport, done: int) -> None:
    BinderExport.objects.filter(pk=export.pk).update(progress_done=done)


def _npages(path: Path) -> int:
    """Nombre de pages d'un PDF, ou 0 s'il est illisible (qpdf : 0 ok, 3 avertissements)."""
    result = subprocess.run(
        ["qpdf", "--show-npages", str(path)], capture_output=True, text=True, timeout=60
    )
    if result.returncode not in (0, 3):
        return 0
    try:
        return int(result.stdout.strip() or 0)
    except ValueError:
        return 0


def _assemble(plan: list[tuple[Path, str | None]], output: Path, workdir: Path) -> None:
    """Assemble les pages avec qpdf, qui lit chaque scan au moment d'écrire (moins de 100 Mo
    de mémoire pour 207 décisions et 720 Mo de PDF), là où une bibliothèque Python les tient
    tous en mémoire."""
    args = ["--empty", "--pages"]
    for path, pages in plan:
        args.append(str(path))
        if pages:
            args.append(pages)
    args += ["--", str(output)]
    argfile = workdir / "qpdf.args"
    argfile.write_text("\n".join(args), encoding="utf-8")
    result = subprocess.run(["qpdf", f"@{argfile}"], capture_output=True, text=True, timeout=1500)
    if result.returncode not in (0, 3):
        raise RuntimeError(f"qpdf : {result.stderr.strip()[:500]}")


def build_export(export: BinderExport) -> None:
    binder = binder_by_key(export.binder_key)
    detail = binder_detail(binder)
    pages = [page for section in detail["sections"] for page in section["pages"]]
    decisions = decisions_by_amm([page["amm_id"] for page in pages])
    attachments = {amm_id: len(items) for amm_id, items in decisions.items()}
    BinderExport.objects.filter(pk=export.pk).update(progress_total=len(pages))

    who = export.created_by.full_name if export.created_by else "AMM GH"
    document = BinderDocument(detail, who, attachments)
    fiches_bytes = document.build()
    fiche_of = {index: amm_id for amm_id, index in document.page_index.items()}

    workdir = Path(tempfile.mkdtemp(prefix="classeur-"))
    try:
        fiches = workdir / "fiches.pdf"
        fiches.write_bytes(fiches_bytes)
        del fiches_bytes
        fiche_count = _npages(fiches)
        # Plan de page : fiches (plage), puis les scans de chaque AMM juste après sa fiche.
        plan: list[tuple[Path, str | None]] = []
        joined = unavailable = done = 0
        pending_from = 1  # première fiche pas encore placée (numérotation qpdf : 1…n)
        for index in sorted(fiche_of):
            amm_id = fiche_of[index]
            scans = decisions.get(amm_id, [])
            done += 1
            if done % 10 == 0:
                _progress(export, done)
            if not scans:
                continue
            plan.append((fiches, f"{pending_from}-{index + 1}"))
            pending_from = index + 2
            for scan in scans:
                path = None
                try:
                    path = _to_pdf(scan, workdir)
                    if not _npages(path):
                        raise ValueError("PDF illisible")
                    joined += 1
                except Exception as exc:  # scan absent du stockage, PDF abîmé…
                    logger.warning("Scan %s non joint au classeur : %s", scan.pk, exc)
                    unavailable += 1
                    path = workdir / f"{scan.pk}-absent.pdf"
                    _placeholder(path, scan, "Fichier illisible ou absent du stockage.")
                plan.append((path, None))
        plan.append((fiches, f"{pending_from}-{fiche_count}"))
        _progress(export, len(pages))

        final = workdir / "classeur.pdf"
        _assemble(plan, final, workdir)
        page_count = _npages(final)

        name = f"Classeur_{export.binder_key}_{timezone.localdate():%Y-%m-%d}.pdf"
        with final.open("rb") as handle:
            export.file.save(name, File(handle), save=False)
        export.size_bytes = final.stat().st_size
        export.page_count = page_count
        export.decisions = joined
        export.unavailable = unavailable
        export.without_scan = sum(1 for page in pages if page["amm_id"] not in decisions)
        export.progress_done = len(pages)
        export.status = BinderExport.Status.READY
        export.finished_at = timezone.now()
        export.save()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    prune(export.binder_key, keep=export.pk)


def prune(binder_key: str, keep=None) -> None:
    """Ne garde que le dernier classeur prêt (et `keep`) : les fichiers pèsent des dizaines
    de Mo. Les échecs anciens sont effacés aussi, sauf les trois derniers."""
    ready = BinderExport.objects.filter(
        binder_key=binder_key, status=BinderExport.Status.READY
    ).order_by(F("finished_at").desc(nulls_last=True), "-created_at")
    kept = [keep] if keep else [ready.values_list("pk", flat=True).first()]
    stale = list(ready.exclude(pk__in=kept)) + list(
        BinderExport.objects.filter(
            binder_key=binder_key, status=BinderExport.Status.FAILED
        ).order_by("-created_at")[3:]
    )
    for old in stale:
        if old.file:
            old.file.delete(save=False)
        old.delete()


def fail(export_id, message: str) -> None:
    BinderExport.objects.filter(pk=export_id).update(
        status=BinderExport.Status.FAILED, error=message[:2000], finished_at=timezone.now()
    )
