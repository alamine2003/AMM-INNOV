"""Import du manifeste des scans classés (« manifeste_scans_amm_gh.csv », classement AMM GHPL).

Troisième étape après le Dashboard et le registre. Le manifeste (une ligne par pièce : pays,
présentation, période, type, date, n°, chemin, SHA-256) passe par Imports Excel, simulation
comprise. Seules les pièces « Exemplaire principal = oui » sont prises.

Pour chaque présentation (pays × présentation du classement) :

- L'AMM est retrouvée comme pour le registre (libellé du Dashboard, puis présentation) ; si elle
  n'existe pas, le produit et l'AMM sont créés depuis les pièces d'origine.
- Le classement fait foi pour les dates : la date d'un dossier « RENOUVELLEMENT n - AAAA-MM-JJ »
  et une date d'origine de fiabilité « haute » ou « lecture visuelle » (de l'année du dossier
  « AMM ORIGINE - AAAA ») corrigent la fiche ; une date moins sûre ne fait que compléter un champ
  vide ; une date approximative ne change rien. Les n° du classement (noms de dossiers, n° de
  décision, plages de décisions groupées) ne font que compléter un n° absent.
- Chaque « RENOUVELLEMENT n » est rapproché d'un renouvellement existant (même date, même n°, ou
  date à moins de 120 jours) ; sinon un dossier déposé sans décision est conclu par elle, sinon
  un renouvellement obtenu est créé. Les renouvellements sont ensuite renumérotés dans l'ordre
  des dates : le dernier obtenu reste celui qui fixe l'échéance.
- Un récépissé de dépôt est rangé avec le dossier en cours, ou avec le renouvellement qu'il a
  précédé (date de dépôt complétée) ; un dépôt antérieur à l'AMM d'origine reste sur l'origine.
  Aucun dossier « déposé » n'est ouvert d'après un scan : c'est le rôle du registre.
- Variations et courriers vont sur la période en vigueur à leur date ; RCP et divers sur l'AMM.

Chaque pièce donne une ligne d'import dont `raw["placement"]` dit où ranger le fichier (AMM,
renouvellement, type, date, titre). Le script `scripts/importer_scans_classement.py` lit ces
lignes et envoie les fichiers (POST /amms/{id}/documents) : les fichiers ne passent pas ici.
"""

import csv
import io
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.db import transaction

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.sequence import resequence
from apps.amm.services.status import compute_amm_state
from apps.catalog.models import Country, Product, ProductRange
from apps.core.dates import today as reference_today

from .models import ImportBatch, ImportRow
from .progress import set_progress
from .registry import COUNTER_KEYS, OUTCOME_COUNTERS, RANGES, UNIDENTIFIED, _Catalog, _plain

logger = logging.getLogger(__name__)

SHEET = "Scans classés"
NOTE = "Classement AMM GHPL (scans classés) : le classement fait foi."
PROGRESS_EVERY = 25
HEADER_MARKERS = ("Presentation (classement)", "Exemplaire principal", "SHA-256")
STRONG = {"haute", "lecture visuelle"}
FILL = {"moyenne", "dashboard (n° amm)", "nom de fichier"}
NEAR = timedelta(days=120)
MAX_ADVANCE = timedelta(days=183)  # recul d'échéance au-delà duquel les corrections attendent
EXTRA_COUNTERS = (
    "amms_created",
    "renewals_created",
    "renewals_concluded",
    "renewals_completed",
    "origins_completed",
    "pieces_placed",
)
COLUMNS = {
    "pays": "Pays",
    "iso2": "ISO2",
    "gamme": "Gamme",
    "presentation": "Presentation (classement)",
    "libelle": "Libelle Dashboard AMM Afrique",
    "periode": "Periode",
    "kind": "Type AMM GH",
    "date": "Date du document (debut de validite)",
    "fiabilite": "Fiabilite date",
    "numero": "N° AMM",
    "principal": "Exemplaire principal",
    "chemin": "Chemin (dans AMM GHPL - CLASSEMENT GENERAL)",
    "nom": "Nom du fichier",
    "sha256": "SHA-256",
}
KINDS = {"AMM", "RECEPISSE", "COURRIER", "AUTRE"}
RANK = {"SKIPPED": 0, "UPDATED": 1, "CREATED": 2, "WARNING": 3, "ERROR": 4}


def _head(source) -> bytes:
    if hasattr(source, "read"):
        if hasattr(source, "seek"):
            source.seek(0)
        head = source.read(4096)
        source.seek(0)
        return head if isinstance(head, bytes) else head.encode()
    with open(source, "rb") as handle:
        return handle.read(4096)


def is_scan_manifest(source) -> bool:
    try:
        first = _head(source).decode("utf-8-sig", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return False
    return all(marker in first for marker in HEADER_MARKERS)


def _read(source) -> list[dict]:
    if hasattr(source, "read"):
        source.seek(0)
        content = source.read()
    else:
        with open(source, "rb") as handle:
            content = handle.read()
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = []
    for line, raw in enumerate(reader, start=2):
        row = {key: str(raw.get(column) or "").strip() for key, column in COLUMNS.items()}
        row["line"] = line
        rows.append(row)
    return rows


def _day(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def clean_number(value: str) -> str:
    """« 9488/13 (decision 0449/2013) » → « 9488/13 » ; « 2178/ 21 » → « 2178/21 »."""
    value = value.split("(")[0].strip()
    return re.sub(r"\s*([/-])\s*", r"\1", value)


def number_key(value: str) -> str:
    """Clé de comparaison : « E-2015-0497 » = « E-2015-497 », « MD/8O1224 » = « MD/801224 »."""
    text = _plain(clean_number(value or ""))
    text = re.sub(r"(?<=\d)O|O(?=\d)", "0", text)  # O lu à la place d'un zéro
    parts = re.findall(r"[A-Z]+|\d+", text)
    return "".join(part.lstrip("0") or "0" if part.isdigit() else part for part in parts)


def plausible_number(value: str) -> bool:
    """Écarte « 18 », « M », « ARTICLE 2 » et les plages de décisions groupées (« 0139 a 0143 »)."""
    plain = _plain(value)
    if len(re.sub(r"[^A-Z0-9]", "", plain)) < 3 or plain.startswith("ARTICLE"):
        return False
    return not re.search(r"\d\s+(A|ET|AU)\s+\d", plain)


ORIGIN_FOLDER = re.compile(r"AMM ORIGINE - ((?:19|20)\d\d)(?! \(APPROX)")
RENEWAL_FOLDER = re.compile(r"RENOUVELLEMENT \d+ - (\d{4}-\d{2}-\d{2})")


@dataclass
class Piece:
    row: dict
    when: date | None
    tier: str  # strong / fill / weak
    outcome: str = "SKIPPED"
    lines: list = field(default_factory=list)
    renewal: Renewal | None = None
    placed: bool = False

    @property
    def period(self) -> str:
        return self.row["periode"].upper()

    @property
    def folder(self) -> str:
        parts = self.row["chemin"].replace("\\", "/").split("/")
        return _plain(parts[-2]) if len(parts) > 1 else ""


def _tier(fiabilite: str) -> str:
    value = fiabilite.strip().lower()
    if value in STRONG:
        return "strong"
    if value in FILL:
        return "fill"
    return "weak"


def _consensus(pieces: list[Piece]) -> tuple[date | None, str, list[date]]:
    """Date retenue pour une période, sa force, et toutes les dates lues (pour le rapprochement).

    Force : strong (corrige), fill (complète), conflict (des dates sûres divergent : la plus
    fréquente est retenue pour créer, rien n'est corrigé), weak (ne change rien).
    """
    seen = sorted({p.when for p in pieces if p.when})
    for tier in ("strong", "fill"):
        dates = Counter(p.when for p in pieces if p.when and p.tier == tier)
        if len(dates) == 1:
            return next(iter(dates)), tier, seen
        if len(dates) > 1:
            best = max(dates.items(), key=lambda item: (item[1], item[0]))[0]
            return best, "conflict", seen
    return (seen[0], "weak", seen) if len(seen) == 1 else (None, "weak", seen)


def origin_dates(pieces: list[Piece]) -> tuple[date | None, str, list[date]]:
    """Date d'origine : seules comptent les pièces datées de l'année du dossier d'origine.

    Le dossier « 1_AMM ORIGINE - 2011 - N° … » contient aussi des pièces postérieures (courriers,
    attestations) : leur date n'est pas celle de l'AMM. Année approximative : rien n'est déduit.
    """
    years = {int(m.group(1)) for p in pieces if (m := ORIGIN_FOLDER.search(p.folder))}
    if len(years) != 1:
        return None, "weak", []
    year = years.pop()
    return _consensus([p for p in pieces if p.when and p.when.year == year])


def renewal_dates(pieces: list[Piece]) -> tuple[date | None, str, list[date]]:
    """Date d'un renouvellement : celle de son dossier (« RENOUVELLEMENT 1 - 2018-03-01 »)."""
    folders = {_day(m.group(1)) for p in pieces if (m := RENEWAL_FOLDER.search(p.folder))}
    folders.discard(None)
    when, tier, seen = _consensus(pieces)
    if len(folders) == 1:
        chosen = folders.pop()
        return chosen, "strong", sorted({*seen, chosen})
    return when, tier, seen


def _number(pieces: list[Piece]) -> tuple[str, bool]:
    """N° unique de la période (et False), ou '' et True si les pièces en donnent plusieurs."""
    numbers = {}
    for piece in pieces:
        value = clean_number(piece.row["numero"])
        if value and plausible_number(value):
            numbers.setdefault(number_key(value), value)
    if len(numbers) == 1:
        return next(iter(numbers.values())), False
    return "", len(numbers) > 1


def _fmt(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


class _Group:
    """Une présentation d'un pays : ses pièces, son AMM, ses renouvellements."""

    def __init__(self, rows: list[dict], context: dict, user, correct: bool = True):
        self.pieces = [Piece(r, _day(r["date"]), _tier(r["fiabilite"])) for r in rows]
        self.context = context
        self.user = user
        # `correct=False` : seconde passe, sans corriger les dates déjà renseignées (voir
        # `shortened`) ; les corrections écartées sont listées dans `corrections`.
        self.correct = correct
        self.corrections: list[str] = []
        self.counters = Counter()
        self.amm: MarketingAuthorization | None = None
        self.renewals: list[Renewal] = []
        self.end_before: date | None = None
        self.status_before = ""
        self.end_after: date | None = None

    @property
    def shortened(self) -> bool:
        """Les corrections avanceraient l'échéance de l'AMM : on ne les applique pas seules.

        Ex. : le Dashboard porte en « origine » la dernière décision (2019) et le classement n'a
        que l'AMM de 2009 ; corriger l'origine ferait passer l'AMM pour expirée. Une date plus
        exacte de quelques jours ou de quelques mois (16/04 → 06/04) s'applique : le classement
        fait foi ; seul un recul de plus de six mois est tenu pour une autre décision.
        """
        if self.end_before is None:
            return False
        return self.end_after is None or self.end_before - self.end_after > MAX_ADVANCE

    # -- helpers ---------------------------------------------------------------------------
    def _save(self, obj, **kwargs):
        obj._change_reason = NOTE
        obj._skip_signals = True  # l'AMM est recalculée une fois, à la fin du groupe
        if self.user is not None:
            obj._history_user = self.user
        obj.save(**kwargs)

    def by_period(self, prefix: str) -> list[Piece]:
        return [p for p in self.pieces if p.period.startswith(prefix)]

    def note(self, pieces, text):
        for piece in pieces:
            piece.lines.append(text)

    def warn(self, pieces, text):
        self.mark(pieces, "WARNING", text)

    def mark(self, pieces, outcome, text):
        """Le résultat le plus parlant l'emporte : à vérifier, puis créé, puis mis à jour."""
        for piece in pieces:
            piece.lines.append(text)
            if RANK[outcome] > RANK[piece.outcome]:
                piece.outcome = outcome

    # -- étapes ----------------------------------------------------------------------------
    def run(self):
        first = self.pieces[0].row
        country = self.context["countries"].get(first["iso2"].upper())
        if country is None:
            self.warn(self.pieces, f"Pays non suivi dans AMM GH : {first['pays']}.")
            return
        presentation = first["presentation"]
        if not presentation or UNIDENTIFIED in _plain(presentation):
            self.warn(self.pieces, "Présentation non identifiée dans le classement : non rangée.")
            return
        catalog = self.context["catalog"]
        labels = [first["libelle"], presentation]
        product = catalog.find(labels, country)
        found = catalog.amm(product, country)
        # Relue en base : l'objet du catalogue a pu être modifié par une passe annulée.
        self.amm = MarketingAuthorization.objects.get(pk=found.pk) if found else None
        origin = self.by_period("ORIGINE")
        if self.amm is None:
            self._create_amm(product, country, origin)
        else:
            state = compute_amm_state(self.amm)
            self.end_before, self.status_before = state.effective_end_date, state.status
            self._origin(origin)
        self.renewals = list(Renewal.objects.filter(amm=self.amm).order_by("sequence"))
        periods = defaultdict(list)
        for piece in self.by_period("RENOUVELLEMENT"):
            periods[piece.period].append(piece)
        infos = {}
        for name in sorted(periods, key=lambda n: int(re.sub(r"\D", "", n) or 0)):
            when, tier, seen = renewal_dates(periods[name])
            number, _divergent = _number(periods[name])
            infos[name] = {
                "pieces": periods[name],
                "when": when,
                "tier": tier,
                "seen": seen,
                "number": number,
                "renewal": None,
            }
        self._match(infos)
        for info in infos.values():
            self._renewal(info)
        if resequence(self.amm):
            self.renewals = list(Renewal.objects.filter(amm=self.amm).order_by("sequence"))
        self._deposits(self.by_period("DEPOT"))
        self._variations([p for p in self.pieces if p.period.startswith("VARIATION")])
        for piece in self.pieces:
            if not piece.period:
                self.warn([piece], "Pièce sans période dans le classement : rangée sur l'AMM.")
        self.amm._change_reason = NOTE
        self.amm._skip_signals = False
        if self.user is not None:
            self.amm._history_user = self.user
        self.amm.save()  # état recalculé depuis les renouvellements, alertes réconciliées
        self.end_after = self.amm.effective_end_date
        if self.status_before and self.amm.status != self.status_before:
            self.warn(
                self.pieces,
                f"statut de l'AMM {self.status_before} → {self.amm.status} d'après le classement "
                f"(échéance {_fmt(self.end_before)} → {_fmt(self.end_after)})",
            )

    def _create_amm(self, product, country, origin):
        first = self.pieces[0].row
        catalog = self.context["catalog"]
        if product is None:
            product = Product(
                name=first["libelle"] or first["presentation"],
                range=self.context["ranges"].get(RANGES.get(_plain(first["gamme"]))),
            )
            self._save(product)
            created = "produit et AMM créés"
        else:
            created = f"AMM créée (produit du catalogue : {product.name})"
        when, _tier, _seen = origin_dates(origin)
        number, _divergent = _number(origin)
        amm = MarketingAuthorization(
            product=product,
            country=country,
            original_number=number,
            original_start_date=when,
            notes=f"{NOTE} Créée d'après les scans classés.",
        )
        self._save(amm)
        catalog.add(amm)
        self.amm = amm
        self.counters["amms_created"] += 1
        detail = f" (n° {number or '—'}, origine {_fmt(amm.original_start_date)})"
        self.mark(origin or self.pieces[:1], "CREATED", created + detail)

    def _origin(self, origin: list[Piece]):
        if not origin:
            return
        amm, changes = self.amm, []
        when, tier, _seen = origin_dates(origin)
        if when and when != amm.original_start_date:
            if amm.original_start_date is None and tier in {"strong", "fill", "conflict"}:
                changes.append(f"date d'origine {_fmt(when)}")
                amm.original_start_date = when
            elif tier == "strong":
                change = f"date d'origine {_fmt(amm.original_start_date)} → {_fmt(when)}"
                self.corrections.append(change)
                if self.correct:
                    changes.append(change)
                    if amm.original_end_date_manual and amm.original_start_date:
                        amm.original_end_date = when + relativedelta(
                            amm.original_end_date, amm.original_start_date
                        )
                    amm.original_start_date = when
            elif tier in {"fill", "conflict"}:
                self.note(
                    origin,
                    f"date d'origine lue {_fmt(when)} (date moins sûre), "
                    f"fiche {_fmt(amm.original_start_date)} : non modifiée",
                )
        # Les n° du classement (noms de dossiers, n° de décision, plages de décisions groupées)
        # sont moins sûrs que la fiche : ils ne font que compléter un n° absent.
        number, divergent = _number(origin)
        if number and not amm.original_number:
            amm.original_number = number
            changes.append(f"n° d'origine {number}")
        elif number and number_key(number) != number_key(amm.original_number):
            self.note(
                origin, f"n° du classement {number} (fiche : {amm.original_number}, conservé)"
            )
        elif divergent and not amm.original_number:
            numbers = sorted({clean_number(p.row["numero"]) for p in origin if p.row["numero"]})
            self.warn(origin, "n° d'origine divergents dans le classement : " + ", ".join(numbers))
        if changes:
            self._save(amm)
            self.counters["origins_completed"] += 1
            self.mark(origin, "UPDATED", "AMM d'origine : " + ", ".join(changes))

    def _match(self, periods: dict[str, dict]) -> None:
        """Rapproche toutes les périodes, par la preuve la plus forte d'abord.

        Même date (début ou décision), puis même n°, puis date à moins de 120 jours : la date
        passe avant le n°, réutilisé d'un renouvellement à l'autre (Congo : le Dashboard porte le
        n° de 2018 sur la décision de 2022).
        """
        claimed: set = set()

        def by_date(info, free):
            return [
                r for r in free if r.start_date in info["seen"] or r.decision_date in info["seen"]
            ]

        def by_number(info, free):
            key = number_key(info["number"])
            return [r for r in free if key and number_key(r.number) == key]

        def by_near(info, free):
            when = info["when"]
            return [r for r in free if when and r.start_date and abs(r.start_date - when) <= NEAR]

        for rule in (by_date, by_number, by_near):
            for info in periods.values():
                if info["renewal"] is not None:
                    continue
                found = rule(info, [r for r in self.renewals if r.pk not in claimed])
                if len(found) == 1:
                    info["renewal"] = found[0]
                    claimed.add(found[0].pk)

    def _renewal(self, info: dict):
        amm, pieces = self.amm, info["pieces"]
        when, tier, seen, number = info["when"], info["tier"], info["seen"], info["number"]
        label = pieces[0].period.capitalize()
        renewal = info["renewal"]
        if renewal is None and when and tier != "weak":
            if amm.original_start_date and when <= amm.original_start_date:
                self.warn(
                    pieces,
                    f"{label} daté du {_fmt(when)}, pas après l'AMM d'origine "
                    f"({_fmt(amm.original_start_date)}) : rangé sur l'AMM, à vérifier",
                )
                return
            renewal = self._conclude(pieces, when, number)
            if renewal is None:
                renewal = Renewal(
                    amm=amm,
                    workflow_status=Renewal.WorkflowStatus.OBTENU,
                    number=number,
                    start_date=when,
                    notes=f"{NOTE} {label} classé.",
                )
                self._save(renewal)
                self.renewals.append(renewal)
                self.counters["renewals_created"] += 1
                self.mark(
                    pieces,
                    "CREATED",
                    f"renouvellement obtenu créé (début {_fmt(when)}, n° {number or '—'})",
                )
        elif renewal is None:
            self.warn(
                pieces,
                f"{label} sans date sûre ({', '.join(_fmt(d) for d in seen) or 'aucune date'}) "
                "et sans renouvellement correspondant : rangé sur l'AMM",
            )
            return
        else:
            self._complete(renewal, pieces, when, tier, number)
        if tier == "conflict":
            self.warn(
                pieces,
                f"{label} : dates divergentes ({', '.join(_fmt(d) for d in seen)}), "
                f"retenu {_fmt(when)}",
            )
        for piece in pieces:
            piece.renewal = renewal

    def _conclude(self, pieces, when, number) -> Renewal | None:
        """Un dossier en cours, sans décision, est conclu par une décision plus récente."""
        obtained = [r.start_date for r in self.renewals if r.start_date]
        if obtained and when <= max(obtained):
            return None
        waiting = [
            r
            for r in self.renewals
            if r.workflow_status in Renewal.OPEN_STATUSES
            and not r.start_date
            and not r.number
            and (r.filing_date is None or r.filing_date <= when)
        ]
        if len(waiting) != 1:
            return None
        renewal = waiting[0]
        renewal.workflow_status = Renewal.WorkflowStatus.OBTENU
        renewal.start_date = when
        renewal.number = number
        renewal.decision_date = renewal.decision_date or when
        self._save(renewal)
        self.counters["renewals_concluded"] += 1
        self.mark(
            pieces,
            "UPDATED",
            f"dossier déposé conclu : renouvellement obtenu (début {_fmt(when)}, "
            f"n° {number or '—'})",
        )
        return renewal

    def _complete(self, renewal, pieces, when, tier, number):
        changes = []
        if when and when != renewal.start_date:
            if renewal.start_date is None and tier in {"strong", "fill", "conflict"}:
                changes.append(f"début {_fmt(when)}")
                renewal.start_date = when
            elif tier == "strong":
                change = f"début {_fmt(renewal.start_date)} → {_fmt(when)}"
                self.corrections.append(f"renouvellement : {change}")
                if self.correct:
                    changes.append(change)
                    if renewal.end_date_manual and renewal.start_date and renewal.end_date:
                        # Durée saisie (Congo : 4 ans) : elle suit la nouvelle date de début.
                        renewal.end_date = when + relativedelta(
                            renewal.end_date, renewal.start_date
                        )
                    renewal.start_date = when
        if number and not renewal.number:
            changes.append(f"n° {number}")
            renewal.number = number
        elif number and number_key(number) != number_key(renewal.number):
            self.note(pieces, f"n° du classement {number} (fiche : {renewal.number}, conservé)")
        if renewal.workflow_status in Renewal.OPEN_STATUSES and renewal.start_date:
            changes.append("statut obtenu (décision classée)")
            renewal.workflow_status = Renewal.WorkflowStatus.OBTENU
        target = f"renouvellement du {_fmt(renewal.start_date)}"
        if changes:
            self._save(renewal)
            self.counters["renewals_completed"] += 1
            self.mark(pieces, "UPDATED", f"{target} : " + ", ".join(changes))

    def _period_at(self, when: date | None) -> Renewal | None:
        if when is None:
            return None
        obtained = [
            r
            for r in self.renewals
            if r.workflow_status == Renewal.WorkflowStatus.OBTENU and r.start_date
        ]
        inside = [r for r in obtained if r.start_date <= when]
        return max(inside, key=lambda r: r.start_date) if inside else None

    def _deposits(self, pieces: list[Piece]):
        amm = self.amm
        filled = {}
        for piece in sorted(pieces, key=lambda p: p.when or date.max):
            when = piece.when
            if when is None:
                self.warn([piece], "dépôt sans date : rangé sur l'AMM")
                continue
            if amm.original_start_date and when < amm.original_start_date:
                piece.lines.append("dépôt de la demande d'origine")
                continue
            same = [r for r in self.renewals if r.filing_date == when]
            obtained = [r.start_date for r in self.renewals if r.start_date]
            latest = max([*obtained, amm.original_start_date or date.min])
            waiting = [
                r
                for r in self.renewals
                if r.workflow_status in Renewal.OPEN_STATUSES
                and (r.filing_date is None or r.filing_date <= when + timedelta(days=30))
            ]
            following = sorted(
                (
                    r
                    for r in self.renewals
                    if r.start_date and when < r.start_date <= when + timedelta(days=3 * 365)
                ),
                key=lambda r: r.start_date,
            )
            if len(same) == 1:
                renewal = same[0]
            elif when >= latest and len(waiting) == 1:
                renewal = waiting[0]
            elif following:
                renewal = following[0]
            else:
                self.warn(
                    [piece],
                    f"dépôt du {_fmt(when)} sans renouvellement correspondant : rangé sur l'AMM",
                )
                continue
            piece.renewal = renewal
            if renewal.filing_date is None and piece.tier != "weak" and renewal.pk not in filled:
                renewal.filing_date = when
                self._save(renewal)
                filled[renewal.pk] = when
                self.counters["renewals_completed"] += 1
                self.mark(
                    [piece],
                    "UPDATED",
                    f"renouvellement {renewal.sequence} : date de dépôt {_fmt(when)}",
                )

    def _variations(self, pieces: list[Piece]):
        for piece in pieces:
            piece.renewal = self._period_at(piece.when)

    # -- rapport ---------------------------------------------------------------------------
    def results(self):
        for piece in self.pieces:
            placement = None
            if self.amm is not None:
                renewal = piece.renewal
                kind = piece.row["kind"].upper()
                placement = {
                    "amm": str(self.amm.pk),
                    "renewal": str(renewal.pk) if renewal else None,
                    "kind": kind if kind in KINDS else "AUTRE",
                    "document_date": (
                        piece.when
                        or (renewal.start_date if renewal else None)
                        or self.amm.original_start_date
                        or reference_today()
                    ).isoformat(),
                    "title": piece.row["nom"][:255],
                    "target": (
                        f"Renouvellement {renewal.sequence}" if renewal else "AMM d'origine"
                    ),
                }
                self.counters["pieces_placed"] += 1
                piece.lines.append(f"à ranger : {placement['target']}")
            yield piece, placement


def _sentence(lines: list[str]) -> str:
    text = "; ".join(dict.fromkeys(lines))
    return (text[:1].upper() + text[1:] + ".") if text else ""


class _Rollback(Exception):
    pass


class _Shortened(Exception):
    pass


def import_scan_manifest(source, batch: ImportBatch | None, dry_run: bool) -> dict[str, dict]:
    """Applique le manifeste ; renvoie les compteurs par pays (« Scans classés — SENEGAL »)."""
    rows = [r for r in _read(source) if r["principal"].lower() == "oui"]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["iso2"].upper(), _plain(row["presentation"]))].append(row)
    user = batch.created_by if batch is not None else None
    sheets: dict[str, dict] = {}
    records: list[ImportRow] = []
    try:
        with transaction.atomic():
            context = {
                "countries": {c.iso2: c for c in Country.objects.all()},
                "ranges": {r.code: r for r in ProductRange.objects.all()},
                "catalog": _Catalog(),
            }
            done = 0
            for index, group_rows in enumerate(groups.values()):
                if batch is not None and index % PROGRESS_EVERY == 0:
                    set_progress(batch.pk, done, len(rows))
                group = _Group(group_rows, context, user)
                try:
                    try:
                        with transaction.atomic():  # un groupe en erreur n'emporte que lui
                            group.run()
                            if group.shortened:
                                raise _Shortened
                            results = list(group.results())
                    except _Shortened:
                        # Corrections écartées : seconde passe qui ne fait que compléter et créer.
                        first = group
                        group = _Group(group_rows, context, user, correct=False)
                        with transaction.atomic():
                            group.run()
                            group.warn(
                                group.pieces,
                                "corrections du classement non appliquées, elles avançaient "
                                f"l'échéance de l'AMM du {_fmt(first.end_before)} au "
                                f"{_fmt(first.end_after)} ("
                                + ", ".join(first.corrections)
                                + ") : à vérifier",
                            )
                            results = list(group.results())
                except Exception as exc:
                    logger.exception("Scans classés, %s", group_rows[0]["presentation"])
                    results = []
                    for piece in group.pieces:
                        piece.outcome, piece.lines = "ERROR", [f"erreur inattendue : {exc}"]
                        results.append((piece, None))
                    group.amm, group.counters = None, Counter()
                done += len(group_rows)
                sheet = f"{SHEET} — {group_rows[0]['pays'] or '?'}"
                counters = sheets.setdefault(
                    sheet, dict.fromkeys((*COUNTER_KEYS, *EXTRA_COUNTERS), 0)
                )
                for key, value in group.counters.items():
                    counters[key] += value
                for piece, placement in results:
                    counters["rows"] += 1
                    counters[OUTCOME_COUNTERS[piece.outcome]] += 1
                    if batch is None:
                        continue
                    raw = {k: v for k, v in piece.row.items() if k != "line"}
                    raw["placement"] = placement
                    records.append(
                        ImportRow(
                            batch=batch,
                            sheet=sheet,
                            row_number=piece.row["line"],
                            raw=raw,
                            outcome=piece.outcome,
                            message=_sentence(piece.lines),
                            amm=None if dry_run or placement is None else group.amm,
                        )
                    )
            if dry_run:
                raise _Rollback
    except _Rollback:
        pass
    if records:
        ImportRow.objects.bulk_create(records, batch_size=500)
    if batch is not None:
        set_progress(batch.pk, len(rows), len(rows))
    return sheets
