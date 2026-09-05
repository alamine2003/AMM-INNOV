# Architecture logicielle et conception — AMM INNOV

| Champ | Valeur |
|---|---|
| Version | 1.0 |
| Date | 04/09/2026 |
| Documents liés | [PRD](../prd.md) · [Architecture technique détaillée](../architecture.md) · [Essentiel](../architecture-essentiels.md) · [Faisabilité fonctionnelle](faisabilite-fonctionnelle.md) · [Faisabilité non fonctionnelle](faisabilite-non-fonctionnelle.md) |

Les diagrammes sont en Mermaid : ils s'affichent dans GitHub, VS Code et la plupart des outils Markdown.

---

## 1. Acteurs

| Acteur | Rôle | Mission |
|---|---|---|
| **Réglementaire pays** | `COUNTRY_REGULATORY` | Dépose les AMM et les renouvellements auprès de l'autorité de son pays et en assure le suivi. |
| **Réglementaire siège** | `HQ_REGULATORY` | Coordonne les activités réglementaires de tous les pays et gère les réglementaires pays (comptes, affectations, priorités, règles d'alerte, imports). |
| **CEO** | `CEO_ADMIN` | Administrateur de l'application, vue d'ensemble sur la couverture réglementaire, les risques et l'activité. |

Héritage des droits : le CEO possède tous les droits du réglementaire siège, qui possède tous les droits du réglementaire pays, étendus à tous les pays.

---

## 2. Architecture logicielle

### 2.1 Vue en couches

```mermaid
flowchart TB
    subgraph Presentation["Présentation — React + TypeScript"]
        P1[Pages et composants MUI]
        P2[Hooks TanStack Query]
        P3[Client WebSocket]
    end
    subgraph Application["Application — Django REST Framework"]
        A1[ViewSets et sérialiseurs]
        A2[Permissions par rôle et périmètre pays]
        A3[Consumers Channels]
    end
    subgraph Domaine["Domaine — services métier"]
        D1[compute_amm_state]
        D2[Workflow de renouvellement]
        D3[Moteur d'alertes]
        D4[Dispatch des notifications]
        D5[Ingestion documentaire]
        D6[Parseur Excel]
    end
    subgraph Infra["Infrastructure"]
        I1[(PostgreSQL)]
        I2[(Redis)]
        I3[Stockage fichiers S3 / volume]
        I4[SMTP]
        I5[Celery worker et beat]
        I6[Grafana]
    end
    P1 --> P2 --> A1
    P3 --> A3
    A1 --> A2 --> D1 & D2 & D3 & D4 & D5 & D6
    D1 & D2 & D3 & D6 --> I1
    D4 --> I4
    D4 --> I2
    D5 --> I3
    A3 --> I2
    I5 --> D1 & D3 & D4 & D6
    I6 --> I1
```

### 2.2 Vue déploiement

```mermaid
flowchart LR
    U[Navigateur] -- HTTPS --> C[Caddy TLS]
    C --> N[nginx : SPA React]
    N -- /api, /ws --> B[Daphne : Django API + WebSocket]
    N -- /grafana --> G[Grafana]
    B --> PG[(PostgreSQL 16)]
    B --> R[(Redis 7)]
    B --> S[(MinIO / volume documents)]
    W[Celery worker] --> PG & R & S
    W --> M[SMTP]
    BT[Celery beat] --> R
    G -- grafana_ro --> PG
```

### 2.3 Modules backend et dépendances

```mermaid
flowchart LR
    accounts --> catalog
    amm --> catalog & accounts
    documents --> amm
    alerts --> amm
    notifications --> alerts & realtime
    realtime --> accounts
    analytics --> amm & documents & alerts
    imports --> catalog & amm
```

---

## 3. Diagramme de cas d'utilisation

```mermaid
flowchart LR
    RP(["👤 Réglementaire pays"])
    RS(["👤 Réglementaire siège"])
    CEO(["👤 CEO"])
    SYS(["⏱ Planificateur"])

    subgraph Suivi["Suivi des AMM"]
        UC1((Consulter mes AMM<br/>et leur statut))
        UC2((Créer / modifier<br/>une AMM))
        UC3((Déposer un<br/>renouvellement))
        UC4((Enregistrer la décision<br/>de l'autorité))
        UC5((Mettre à jour<br/>l'état du dossier))
    end
    subgraph Docs["Dossier documentaire"]
        UC6((Téléverser le scan<br/>PDF d'une AMM))
        UC7((Consulter la chronologie<br/>des scans))
        UC8((Télécharger le<br/>dossier ZIP))
        UC9((Supprimer<br/>un document))
    end
    subgraph Alertes["Alertes"]
        UC10((Recevoir une alerte<br/>de dépôt J-180))
        UC11((Acquitter / assigner<br/>une alerte))
        UC12((Paramétrer les<br/>règles d'alerte))
    end
    subgraph Coord["Coordination"]
        UC13((Consulter la vue<br/>consolidée Afrique))
        UC14((Gérer les réglementaires<br/>pays et leurs pays))
        UC15((Importer le<br/>classeur Excel))
        UC16((Exporter Excel / CSV))
        UC17((Corriger les anomalies<br/>d'import))
    end
    subgraph Admin["Administration"]
        UC18((Gérer les comptes<br/>siège))
        UC19((Gérer les référentiels<br/>pays, gammes, produits))
        UC20((Consulter Grafana<br/>et l'audit))
    end
    subgraph Auto["Traitements automatiques"]
        UC21((Recalculer les<br/>statuts))
        UC22((Évaluer les règles<br/>et notifier))
        UC23((Envoyer le digest<br/>hebdomadaire))
    end

    RP --> UC1 & UC2 & UC3 & UC4 & UC5 & UC6 & UC7 & UC8 & UC10 & UC11
    RS --> UC12 & UC13 & UC14 & UC15 & UC16 & UC17 & UC19
    RS -. hérite .-> RP
    CEO --> UC9 & UC18 & UC20
    CEO -. hérite .-> RS
    SYS --> UC21 & UC22 & UC23
    UC3 -. include .-> UC6
    UC4 -. include .-> UC6
    UC22 -. extend .-> UC10
```

### 3.1 Fiches des cas d'utilisation majeurs

**UC3 — Déposer un renouvellement**
- Acteur : réglementaire pays.
- Précondition : AMM dans son périmètre ; renouvellement en `PLANIFIE` ou `EN_PREPARATION` (créé automatiquement à l'alerte J-365 ou manuellement).
- Scénario nominal : ouvrir la fiche AMM → onglet Renouvellements → « Déposer » → saisir la date de dépôt, joindre le récépissé PDF → valider.
- Postconditions : renouvellement en `DEPOSE` ; alertes J-180/J-90/J-30 ouvertes résolues en `AUTO_FILED` ; statut AMM `IN_PROCESS` si l'AMM d'origine est expirée, sinon inchangé ; urgence `EN_INSTRUCTION` ; événement temps réel diffusé au pays et au siège ; entrée d'audit.
- Exceptions : date de dépôt manquante → refus ; transition invalide → refus avec message.

**UC4 — Enregistrer la décision de l'autorité**
- Précondition : renouvellement en `DEPOSE` ou `EN_INSTRUCTION`.
- Nominal : « Obtenu » → saisir le nouveau numéro, la date de début (date de fin calculée +5 ans, modifiable), joindre le scan de l'AMM → valider.
- Postconditions : renouvellement `OBTENU` ; date de fin effective mise à jour ; statut `VALIDE` ; alertes résolues `AUTO_RENEWED` ; le scan devient le premier élément de la chronologie documentaire avec le badge « En vigueur ».
- Alternative : « Rejeté » → date de décision et motif ; un nouveau renouvellement peut être planifié.

**UC14 — Gérer les réglementaires pays**
- Acteur : réglementaire siège.
- Nominal : créer un compte (email, nom, mot de passe initial), rôle `COUNTRY_REGULATORY`, cocher les pays → enregistrer. Le compte reçoit immédiatement les alertes de ses pays.
- Règles : le siège ne peut créer ni modifier un compte `HQ_REGULATORY` ou `CEO_ADMIN` ; la désactivation est immédiate (jeton révoqué).

**UC22 — Évaluer les règles et notifier** (automatique, 00:15)
- Pour chaque AMM et chaque règle applicable, créer l'alerte si l'échéance est atteinte et qu'elle n'existe pas encore ; notifier les destinataires selon leur rôle et leur périmètre ; envoyer les emails.

---

## 4. Diagramme de classes

```mermaid
classDiagram
    direction LR

    class User {
        +UUID id
        +str email
        +str first_name
        +str last_name
        +Role role
        +bool is_active
        +countries() Country[]
        +can_access(country) bool
        +is_global() bool
    }
    class Role {
        <<enumeration>>
        CEO_ADMIN
        HQ_REGULATORY
        COUNTRY_REGULATORY
    }

    class Country {
        +UUID id
        +str iso2
        +str name
        +str authority
        +int validity_years = 5
        +int filing_lead_months = 6
        +str timezone
    }
    class ProductRange {
        +UUID id
        +str code
        +str label
    }
    class Product {
        +UUID id
        +str name
        +str dci
        +str dosage
        +str form
        +str presentation
        +bool is_active
        +coverage() CountryCoverage[]
    }
    class ProductAlias {
        +UUID id
        +str raw_name
    }

    class MarketingAuthorization {
        +UUID id
        +str original_number
        +date original_start_date
        +date original_end_date
        +bool original_end_date_manual
        +AmmStatus status
        +Urgency urgency
        +date effective_end_date
        +date filing_deadline
        +DossierState dossier_state
        +str notes
        +recompute(today) void
        +current_renewal() Renewal
        +has_current_scan() bool
    }
    class AmmStatus {
        <<enumeration>>
        VALIDE
        EXPIRE
        IN_PROCESS
        INDETERMINE
    }
    class Urgency {
        <<enumeration>>
        OK
        A_PLANIFIER
        DEPOT_URGENT
        CRITIQUE
        EXPIRE
        EN_INSTRUCTION
    }
    class DossierState {
        <<enumeration>>
        COMPLET
        INCOMPLET
        INCONNU
    }

    class Renewal {
        +UUID id
        +int sequence
        +WorkflowStatus workflow_status
        +date filing_date
        +date decision_date
        +str number
        +date start_date
        +date end_date
        +bool end_date_manual
        +str notes
        +transition(to, actor, fields) void
        +is_pending() bool
    }
    class WorkflowStatus {
        <<enumeration>>
        PLANIFIE
        EN_PREPARATION
        DEPOSE
        EN_INSTRUCTION
        OBTENU
        REJETE
        ABANDONNE
    }

    class Document {
        +UUID id
        +DocumentKind kind
        +str title
        +date document_date
        +File file
        +str sha256
        +int size_bytes
        +int page_count
        +int version
        +bool is_current
        +datetime uploaded_at
        +datetime archived_at
        +replace(new_file, actor) Document
        +archive(actor) void
    }
    class DocumentKind {
        <<enumeration>>
        AMM
        RECEPISSE
        COURRIER
        AUTRE
    }

    class AlertRule {
        +UUID id
        +str code
        +int offset_days
        +Severity severity
        +Role[] roles
        +Channel[] channels
        +bool only_if_not_filed
        +bool is_active
        +applies_to(amm, today) bool
    }
    class Alert {
        +UUID id
        +date due_date
        +AlertStatus status
        +datetime triggered_at
        +datetime acknowledged_at
        +datetime resolved_at
        +Resolution resolution
        +str comment
        +acknowledge(actor) void
        +assign(user, actor) void
        +resolve(resolution, comment) void
    }
    class Notification {
        +UUID id
        +Channel channel
        +str title
        +str body
        +str link
        +datetime sent_at
        +datetime read_at
        +mark_read() void
    }

    class ImportBatch {
        +UUID id
        +File file
        +str status
        +json summary
        +datetime created_at
        +run(today) void
    }
    class ImportRow {
        +UUID id
        +str sheet
        +int row_number
        +json raw
        +str outcome
        +str message
    }

    class StatusService {
        <<service>>
        +compute_amm_state(amm, today) State
        +apply_state(amm) void
        +recompute_all(today) int
    }
    class WorkflowService {
        <<service>>
        +transition(renewal, to, actor, fields) Renewal
        +allowed_transitions(renewal) WorkflowStatus[]
    }
    class AlertEngine {
        <<service>>
        +evaluate_rules(today) Alert[]
        +reconcile(amm) int
    }
    class NotificationDispatcher {
        <<service>>
        +dispatch(alert) Notification[]
        +send_weekly_digest() int
    }
    class DocumentIngestor {
        <<service>>
        +ingest(amm, renewal, file, kind, date, actor) Document
        +build_archive(amm) bytes
    }
    class ExcelImporter {
        <<service>>
        +parse(workbook) ParsedRow[]
        +apply(batch, today) Summary
    }
    class RealtimePublisher {
        <<service>>
        +publish(group, event) void
    }

    User "1" --> "0..*" Country : countries
    User --> Role
    ProductRange "1" --> "0..*" Product
    Product "1" --> "0..*" ProductAlias
    Product "1" --> "0..*" MarketingAuthorization
    Country "1" --> "0..*" MarketingAuthorization
    User "0..1" --> "0..*" MarketingAuthorization : owner
    MarketingAuthorization --> AmmStatus
    MarketingAuthorization --> Urgency
    MarketingAuthorization --> DossierState
    MarketingAuthorization "1" *-- "0..*" Renewal : renewals
    Renewal --> WorkflowStatus
    MarketingAuthorization "1" *-- "0..*" Document : documents
    Renewal "0..1" --> "0..*" Document
    Document --> DocumentKind
    Document "0..1" --> "0..1" Document : replaces
    User "1" --> "0..*" Document : uploaded_by
    Country "0..1" --> "0..*" AlertRule
    AlertRule "1" --> "0..*" Alert
    MarketingAuthorization "1" --> "0..*" Alert
    User "0..1" --> "0..*" Alert : assigned_to
    Alert "0..1" --> "0..*" Notification
    User "1" --> "0..*" Notification
    ImportBatch "1" *-- "0..*" ImportRow
    User "1" --> "0..*" ImportBatch : created_by

    StatusService ..> MarketingAuthorization
    StatusService ..> Renewal
    WorkflowService ..> Renewal
    WorkflowService ..> StatusService
    WorkflowService ..> AlertEngine
    AlertEngine ..> AlertRule
    AlertEngine ..> Alert
    AlertEngine ..> NotificationDispatcher
    NotificationDispatcher ..> Notification
    NotificationDispatcher ..> RealtimePublisher
    DocumentIngestor ..> Document
    ExcelImporter ..> ImportBatch
    ExcelImporter ..> MarketingAuthorization
```

### 4.1 Invariants
- Une `MarketingAuthorization` est unique par (produit, pays).
- Au plus un `Renewal` non terminal (`PLANIFIE`, `EN_PREPARATION`, `DEPOSE`, `EN_INSTRUCTION`) par AMM.
- `Alert` unique par (AMM, règle, échéance).
- `Document.is_current` est vrai pour au plus un document par chaîne de versions.
- `status`, `urgency`, `effective_end_date` et `filing_deadline` ne sont jamais saisis : ils sont toujours produits par `StatusService`.

---

## 5. Diagrammes de séquence

### 5.1 Connexion et chargement du périmètre

```mermaid
sequenceDiagram
    actor RP as Réglementaire pays
    participant UI as React
    participant API as Django API
    participant DB as PostgreSQL
    participant WS as Channels

    RP->>UI: email + mot de passe
    UI->>API: POST /auth/login
    API->>DB: vérifier l'utilisateur (Argon2)
    DB-->>API: user, rôle, pays
    API-->>UI: access (15 min), refresh (7 j), user
    UI->>API: GET /me
    API-->>UI: rôle = COUNTRY_REGULATORY, countries = [SN, ML]
    UI->>WS: connexion ws/ (sous-protocole amm.jwt + access)
    WS->>WS: valider le JWT, calculer les groupes
    WS-->>UI: abonné à user.{id}, country.SN, country.ML
    UI->>API: GET /amms?country=SN
    API->>API: filtrer le queryset sur le périmètre
    API-->>UI: page 1 (50 AMM)
```

### 5.2 Dépôt d'un renouvellement avec résolution automatique de l'alerte et diffusion temps réel

```mermaid
sequenceDiagram
    actor RP as Réglementaire pays
    participant UI as React
    participant API as Django API
    participant WF as WorkflowService
    participant ST as StatusService
    participant AE as AlertEngine
    participant DB as PostgreSQL
    participant PUB as RealtimePublisher
    participant R as Redis
    actor RS as Réglementaire siège (navigateur)

    RP->>UI: « Déposer » + date de dépôt + récépissé PDF
    UI->>API: POST /renewals/{id}/transition {to: DEPOSE, filing_date}
    API->>API: permission : pays ∈ périmètre ?
    API->>WF: transition(renewal, DEPOSE, actor, filing_date)
    WF->>WF: vérifier la transition et les champs requis
    WF->>DB: UPDATE renewal (workflow_status, filing_date) + historique
    WF->>ST: apply_state(amm)
    ST->>DB: UPDATE amm (status, urgency=EN_INSTRUCTION, dates)
    WF->>AE: reconcile(amm)
    AE->>DB: alertes OPEN J-180/J-90/J-30 → RESOLVED (AUTO_FILED)
    WF-->>API: renewal
    API->>PUB: publish(country.SN, {type: renewal.transitioned, id})
    PUB->>R: group_send
    API-->>UI: 200 renewal
    UI->>API: POST /renewals/{id}/documents (multipart, kind=RECEPISSE)
    API->>DB: INSERT document (sha256, document_date=filing_date)
    API->>PUB: publish(country.SN, {type: document.created})
    R-->>RS: événement WebSocket
    RS->>API: GET /alerts?status=OPEN (invalidation TanStack Query)
    API-->>RS: liste à jour (alerte disparue)
```

### 5.3 Traitement nocturne : recalcul, évaluation des règles, notification J-180

```mermaid
sequenceDiagram
    participant BEAT as Celery beat
    participant W as Celery worker
    participant ST as StatusService
    participant AE as AlertEngine
    participant ND as NotificationDispatcher
    participant DB as PostgreSQL
    participant PUB as RealtimePublisher
    participant SMTP as Serveur email
    actor RP as Réglementaire pays

    BEAT->>W: 00:05 recompute_all_statuses
    W->>ST: recompute_all(today)
    ST->>DB: UPDATE status/urgency de chaque AMM
    W->>PUB: publish(global, dashboard.refresh)
    BEAT->>W: 00:15 evaluate_alert_rules
    W->>AE: evaluate_rules(today)
    AE->>DB: règles actives, AMM avec effective_end_date − 180 j ≤ today, sans dépôt
    loop pour chaque AMM éligible
        AE->>DB: INSERT alert (amm, J-180, due_date) si absente
        AE->>ND: dispatch(alert)
        ND->>DB: destinataires = rôles de la règle ∩ périmètre pays
        ND->>DB: INSERT notification IN_APP et EMAIL
        ND->>PUB: publish(user.{id}, notification.created)
        ND->>W: send_alert_email.delay(notification)
        W->>SMTP: email « Dépôt à effectuer avant le JJ/MM/AAAA »
    end
    PUB-->>RP: toast + badge cloche (si connecté)
    SMTP-->>RP: email avec lien vers l'AMM
```

### 5.4 Téléversement d'un scan d'AMM et consultation en chronologie inverse

```mermaid
sequenceDiagram
    actor RP as Réglementaire pays
    participant UI as React
    participant API as Django API
    participant DI as DocumentIngestor
    participant S as Stockage (S3 / volume)
    participant DB as PostgreSQL

    RP->>UI: glisser-déposer AMM_2029.pdf, kind=AMM, date=15/02/2029
    UI->>UI: SHA-256 côté client (pré-contrôle doublon)
    UI->>API: POST /renewals/{id}/documents (multipart)
    API->>DI: ingest(amm, renewal, file, AMM, date, actor)
    DI->>DI: vérifier MIME réel, taille ≤ 25 Mo, assainir le PDF
    DI->>DB: doublon sha256 sur cette AMM ?
    DI->>S: écrire documents/SN/produit/amm/2029-02-15_AMM_v1_x.pdf
    DI->>DB: INSERT document (version 1, is_current)
    DI-->>API: document
    API-->>UI: 201
    UI->>API: GET /amms/{id}/documents?group=period
    API->>DB: SELECT ... ORDER BY document_date DESC, uploaded_at DESC
    API-->>UI: [Renouvellement 2 (en vigueur) → AMM_2029.pdf], [Renouvellement 1 → ...], [Origine → ...]
    RP->>UI: clic sur AMM_2029.pdf
    UI->>API: GET /documents/{id}/file (Bearer)
    API->>API: contrôle du périmètre pays
    API->>S: lecture du fichier
    API-->>UI: flux PDF (inline)
    UI->>UI: visionneuse pdf.js
```

### 5.5 Import du classeur Excel par le siège

```mermaid
sequenceDiagram
    actor RS as Réglementaire siège
    participant UI as React
    participant API as Django API
    participant W as Celery worker
    participant IMP as ExcelImporter
    participant DB as PostgreSQL

    RS->>UI: choisir le classeur .xlsx
    UI->>API: POST /imports (multipart)
    API->>DB: INSERT import_batch (PENDING)
    API->>W: run_import.delay(batch_id)
    API-->>UI: 202 {id, status: PENDING}
    W->>IMP: apply(batch, today)
    loop pour chaque onglet au format normalisé
        IMP->>IMP: onglet → pays, en-tête vérifié
        loop pour chaque ligne avec NOM
            IMP->>IMP: normaliser gamme et libellé, parser les dates, numéro en chaîne
            IMP->>DB: upsert product/alias, upsert amm, renewal
            IMP->>IMP: recalculer le statut, comparer à la colonne STATUT
            IMP->>DB: INSERT import_row (CREATED/UPDATED/WARNING/ERROR)
        end
    end
    IMP->>DB: UPDATE import_batch (DONE, summary)
    W->>W: refresh_analytics_views
    UI->>API: GET /imports/{id} (polling ou événement)
    API-->>UI: résumé : créées, mises à jour, erreurs, divergences
    RS->>UI: ouvrir les lignes en erreur et corriger
```

---

## 6. Diagrammes d'activités

### 6.1 Cycle de vie d'une AMM et processus de renouvellement

```mermaid
flowchart TD
    A([AMM obtenue<br/>date de début D]) --> B[Date de fin = D + 5 ans<br/>Statut VALIDE]
    B --> C{Fin − 12 mois<br/>atteinte ?}
    C -- non --> B
    C -- oui --> D[Alerte J-365<br/>Renouvellement PLANIFIE]
    D --> E[Réglementaire pays :<br/>constitution du dossier<br/>EN_PREPARATION]
    E --> F{Fin − 6 mois<br/>atteinte ?}
    F -- dossier déposé --> H
    F -- non déposé --> G[Alerte J-180 : deadline de dépôt<br/>email pays + siège]
    G --> G2{Déposé ?}
    G2 -- non, fin − 3 mois --> G3[Alerte J-90<br/>escalade siège]
    G3 --> G4{Déposé ?}
    G4 -- non, fin − 1 mois --> G5[Alerte J-30<br/>escalade CEO]
    G5 --> G6{Déposé ?}
    G6 -- non, fin dépassée --> X[Statut EXPIRE<br/>Alerte J0<br/>Rupture de commercialisation]
    X --> E
    G2 -- oui --> H
    G4 -- oui --> H
    G6 -- oui --> H
    H[Renouvellement DEPOSE<br/>date de dépôt + récépissé PDF<br/>alertes résolues AUTO_FILED] --> I[EN_INSTRUCTION<br/>urgence EN_INSTRUCTION]
    I --> J{Décision de<br/>l'autorité}
    J -- délai dépassé --> K[Alerte DECISION<br/>relance de l'autorité]
    K --> I
    J -- rejet --> L[REJETE<br/>motif enregistré]
    L --> E
    J -- accord --> M[OBTENU : nouveau numéro,<br/>nouvelle date de début,<br/>scan AMM en tête de chronologie]
    M --> B
    E -. retrait du produit .-> N([ABANDONNE])
```

### 6.2 Traitement nocturne automatique

```mermaid
flowchart TD
    S([00:05 — Celery beat]) --> A[Pour chaque AMM :<br/>compute_amm_state today]
    A --> B{État modifié ?}
    B -- oui --> C[Écrire status, urgency,<br/>effective_end_date, filing_deadline]
    B -- non --> D
    C --> D[Publier dashboard.refresh]
    D --> E([00:15 — evaluate_alert_rules])
    E --> F[Charger les règles actives<br/>règle pays > règle globale]
    F --> G[Pour chaque règle × AMM éligible]
    G --> H{Alerte amm × règle × échéance<br/>existe déjà ?}
    H -- oui --> G
    H -- non --> I{only_if_not_filed et<br/>dépôt enregistré ?}
    I -- oui --> G
    I -- non --> J[Créer l'alerte OPEN]
    J --> K[Résoudre les destinataires :<br/>rôles de la règle ∩ périmètre pays]
    K --> L[Créer les notifications IN_APP<br/>publier sur user.id]
    L --> M{Canal EMAIL ?}
    M -- oui --> N[send_alert_email avec retry]
    M -- non --> G
    N --> G
    G -- terminé --> O([00:30 — refresh_analytics_views])
    O --> P[REFRESH MATERIALIZED VIEW<br/>mv_country_kpi, mv_expiry_pipeline]
    P --> Q([Fin])
```

### 6.3 Coordination par le réglementaire siège

```mermaid
flowchart TD
    A([Lundi 08:00 — digest reçu]) --> B[Ouvrir le dashboard Afrique]
    B --> C{Pays avec AMM en<br/>DEPOT_URGENT ou CRITIQUE ?}
    C -- non --> Z([Rien à faire])
    C -- oui --> D[Ouvrir le dashboard pays]
    D --> E{Réglementaire pays<br/>affecté et actif ?}
    E -- non --> F[Créer ou réactiver le compte,<br/>affecter le pays]
    F --> G
    E -- oui --> G[Assigner les alertes ouvertes<br/>avec commentaire de priorité]
    G --> H{Réponse sous 5 jours ?}
    H -- non --> I[Le siège dépose lui-même<br/>ou relance par email]
    H -- oui --> J[Suivre la transition DEPOSE<br/>en temps réel]
    I --> J
    J --> K{Dossier INCOMPLET ?}
    K -- oui --> L[Demander les pièces manquantes,<br/>mettre à jour l'état du dossier]
    K -- non --> Z
    L --> Z
```

### 6.4 Téléversement et classement d'un document

```mermaid
flowchart TD
    A([Fichier déposé]) --> B{Type réel PDF, JPEG ou PNG<br/>et taille ≤ 25 Mo ?}
    B -- non --> E1([Refus : type ou taille])
    B -- oui --> C{Image ?}
    C -- oui --> D[Convertir en PDF]
    C -- non --> F[Assainir le PDF]
    D --> F
    F --> G[Calculer SHA-256]
    G --> H{Même empreinte déjà<br/>présente sur cette AMM ?}
    H -- oui --> E2([Refus : doublon])
    H -- non --> I{Date du document<br/>fournie ?}
    I -- non --> J[Date = début du renouvellement<br/>sinon début de l'AMM d'origine]
    I -- oui --> K
    J --> K[Écrire le fichier<br/>chemin préfixé par la date]
    K --> L[Enregistrer les métadonnées<br/>version 1, is_current]
    L --> M[Tâche : page_count et miniature]
    M --> N[Publier document.created]
    N --> O([Affiché en tête de la chronologie<br/>si c'est le plus récent])
```

---

## 7. Matrice rôles × cas d'utilisation

| Cas d'utilisation | Réglementaire pays | Réglementaire siège | CEO |
|---|---|---|---|
| Consulter les AMM | Ses pays | Tous | Tous |
| Créer / modifier une AMM | Ses pays | Tous | Tous |
| Déposer / faire aboutir un renouvellement | Ses pays | Tous | Tous |
| Téléverser, remplacer un document | Ses pays | Tous | Tous |
| Supprimer (archiver) un document | — | — | ✔ |
| Acquitter / assigner une alerte | Ses pays | Tous | Tous |
| Paramétrer les règles d'alerte | — | ✔ | ✔ |
| Gérer les réglementaires pays | — | ✔ | ✔ |
| Gérer les comptes siège | — | — | ✔ |
| Gérer les référentiels | — | ✔ | ✔ |
| Importer / exporter | Export de ses pays | ✔ | ✔ |
| Dashboards Afrique et Grafana | Ses pays | ✔ | ✔ |
| Consulter l'audit | Ses pays | ✔ | ✔ |

---

## 8. Correspondance conception → code

| Élément de conception | Emplacement dans le code |
|---|---|
| Classes métier | `backend/apps/<app>/models.py` |
| `StatusService` | `backend/apps/amm/services/status.py` |
| `WorkflowService` | `backend/apps/amm/services/workflow.py` |
| `AlertEngine` | `backend/apps/alerts/services/engine.py` |
| `NotificationDispatcher` | `backend/apps/notifications/services.py` |
| `DocumentIngestor` | `backend/apps/documents/services/ingest.py` |
| `ExcelImporter` | `backend/apps/imports/excel_parser.py` |
| `RealtimePublisher` | `backend/apps/realtime/publisher.py` |
| Permissions rôle × périmètre | `backend/apps/accounts/permissions.py` |
| Tâches planifiées | `backend/config/celery.py`, `backend/apps/*/tasks.py` |
| Écrans | `frontend/src/features/*` |
| Client temps réel | `frontend/src/realtime/` |
| Dashboards Grafana | `grafana/dashboards/` |
| Pipeline CI/CD | `.github/workflows/` |
