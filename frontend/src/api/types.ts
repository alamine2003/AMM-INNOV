export type Role = 'CEO_ADMIN' | 'HQ_REGULATORY' | 'COUNTRY_REGULATORY';

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  countries: string[];
  is_active?: boolean;
}

export interface UserWrite {
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  countries: string[];
  is_active?: boolean;
  password?: string;
}

export interface LoginResponse {
  access: string;
  user: User;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Country {
  id: string;
  iso2: string;
  name: string;
  authority: string;
  validity_years: number;
  timezone: string;
}

export interface ProductRange {
  id: string;
  code: string;
  label: string;
}

export interface Product {
  id: string;
  name: string;
  range: string | null;
  range_code: string;
  dci: string;
  dosage: string;
  form: string;
  presentation: string;
  is_active: boolean;
  aliases: string[];
}

/** Statut de validité de l'AMM actuelle ; INDETERMINE = aucune date de fin connue. */
export type AmmStatus = 'VALIDE' | 'A_RENOUVELER' | 'EXPIRE' | 'INDETERMINE';
export type Urgency = 'OK' | 'A_PLANIFIER' | 'DEPOT_URGENT' | 'CRITIQUE' | 'EXPIRE';
export type DossierState = 'COMPLET' | 'INCOMPLET';
export type WorkflowStatus =
  'PLANIFIE' | 'EN_PREPARATION' | 'DEPOSE' | 'EN_INSTRUCTION' | 'OBTENU' | 'REJETE' | 'ABANDONNE';

export interface LastRenewal {
  id: string;
  sequence: number;
  workflow_status: WorkflowStatus;
  number: string | null;
  start_date: string | null;
  end_date: string | null;
}

export interface Amm {
  id: string;
  product: string;
  product_name: string;
  range_code: string;
  country: string;
  country_iso2: string;
  country_name: string;
  holder?: string;
  original_number: string | null;
  original_start_date: string | null;
  original_end_date: string | null;
  original_end_date_manual: boolean;
  status: AmmStatus;
  urgency: Urgency;
  effective_end_date: string | null;
  /** Dépôt idéal : fin − 6 mois (objectif interne). */
  ideal_filing_date: string | null;
  /** Limite agence : fin − 3 mois. */
  agency_filing_deadline: string | null;
  dossier_state: DossierState;
  notes: string;
  owner: string | null;
  has_current_scan: boolean;
  /** Points à vérifier plus tard (import de dossiers) encore ouverts. */
  open_review_points?: number;
  last_renewal: LastRenewal | null;
  updated_at: string;
}

export interface AmmWrite {
  product: string;
  country: string;
  original_number?: string | null;
  original_start_date?: string | null;
  original_end_date?: string | null;
  original_end_date_manual?: boolean;
  dossier_state?: DossierState;
  notes?: string;
  owner?: string | null;
}

export interface AmmFilters {
  country?: string;
  range?: string;
  status?: AmmStatus | '';
  /** Une urgence, ou plusieurs séparées par des virgules (`urgency__in` côté API). */
  urgency?: Urgency | string;
  dossier_state?: DossierState | '';
  expires_before?: string;
  has_current_scan?: 'true' | 'false' | '';
  search?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export interface HistoryChange {
  field: string;
  old: unknown;
  new: unknown;
}

export interface HistoryEntry {
  date: string;
  user_email: string | null;
  type: string;
  /** `amm`, `renewal` ou `document` */
  model?: string;
  object_id?: string;
  changes: HistoryChange[];
  source?: string;
  reason?: string;
  confidence?: number;
  proof_file_id?: string | null;
  batch_id?: string;
  document_id?: string | null;
}

export interface Renewal {
  id: string;
  amm_id: string;
  sequence: number;
  workflow_status: WorkflowStatus;
  filing_date: string | null;
  decision_date: string | null;
  number: string | null;
  start_date: string | null;
  end_date: string | null;
  end_date_manual: boolean;
  notes: string;
  created_at: string;
}

export interface RenewalWrite {
  notes?: string;
  /** Déduit de la saisie : une date de début vaut décision obtenue, sinon le renouvellement
   * est seulement planifié. À ne préciser que pour forcer l'un des deux. */
  workflow_status?: WorkflowStatus;
  filing_date?: string | null;
  decision_date?: string | null;
  number?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface TransitionPayload {
  to: WorkflowStatus;
  filing_date?: string;
  decision_date?: string;
  number?: string;
  start_date?: string;
  end_date?: string;
  notes?: string;
}

export type DocumentKind = 'AMM' | 'RECEPISSE' | 'COURRIER' | 'AUTRE';

export interface AmmDocument {
  id: string;
  /** Identifiant de l'AMM (champ `amm_id` de l'API). */
  amm_id: string;
  renewal_id: string | null;
  renewal_sequence: number | null;
  country_iso2: string;
  product_name: string;
  /** @deprecated forme interne des mocks ; l'API expose `amm_id`. */
  amm?: string;
  /** @deprecated forme interne des mocks ; l'API expose `renewal_id`. */
  renewal?: string | null;
  kind: DocumentKind;
  title: string;
  document_date: string;
  sha256: string;
  size_bytes: number;
  page_count: number | null;
  version: number;
  replaces: string | null;
  is_current: boolean;
  uploaded_by_email: string;
  uploaded_at: string;
  archived_at: string | null;
  file_url: string;
  download_url?: string;
  filename?: string;
}

export interface DocumentPeriod {
  period: 'RENEWAL' | 'ORIGINAL';
  sequence: number | null;
  label: string;
  documents: AmmDocument[];
}

export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED';
export type Severity = 'INFO' | 'WARNING' | 'CRITICAL';

export interface Alert {
  id: string;
  amm_id: string;
  country_iso2: string;
  country_name?: string;
  product_name: string;
  amm_status?: AmmStatus;
  amm_urgency?: Urgency;
  effective_end_date: string | null;
  /** @deprecated forme interne des mocks ; l'API expose `amm_id`. */
  amm?: string;
  rule?: string;
  rule_code: string;
  severity: Severity;
  due_date: string;
  status: AlertStatus;
  assigned_to: string | null;
  assigned_to_email: string | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
  comment: string | null;
}

export interface AlertFilters {
  status?: AlertStatus | '';
  country?: string;
  severity?: Severity | '';
  assigned_to?: 'me' | '';
  page?: number;
  page_size?: number;
}

export interface AlertRule {
  id: string;
  code: string;
  country: string | null;
  offset_days: number;
  severity: Severity;
  roles: Role[];
  channels: string[];
  only_if_not_filed: boolean;
  is_active: boolean;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  link: string | null;
  channel: 'IN_APP' | 'EMAIL';
  sent_at: string | null;
  read_at: string | null;
}

export interface AfricaRow {
  country_iso2: string;
  country_name: string;
  total: number;
  valid: number;
  to_renew: number;
  expired: number;
  undetermined: number;
  pct_valid: number;
  expiring_6m: number;
  expiring_12m: number;
  pct_complete: number;
}

export interface AfricaAnalytics {
  rows: AfricaRow[];
  total: AfricaRow;
}

export interface CountryAnalytics {
  by_range_status: { range: string; status: AmmStatus; count: number }[];
  pipeline: { month: string; count: number }[];
  priorities: Amm[];
}

export interface DuplicateProduct {
  id: string;
  name: string;
  range_code: string | null;
  amm_count: number;
  alias_count: number;
  countries: string[];
}

export interface DuplicateGroup {
  key: string;
  products: DuplicateProduct[];
  suggested_keep_id: string;
  conflict_countries: string[];
  conflict: boolean;
}

export interface MergeDuplicatesResult {
  dry_run: boolean;
  merged_groups: number;
  merged_products: number;
  conflicts: DuplicateGroup[];
}

export interface CoverageCell {
  country_iso2: string;
  country_name: string;
  status: AmmStatus | null;
  effective_end_date: string | null;
  /** false pour un réglementaire pays hors de son périmètre : l'API ne renvoie alors aucune donnée. */
  in_scope?: boolean;
}

export interface ImportBatch {
  id: string;
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | string;
  /** Simulation : rapport produit, aucune donnée écrite. */
  dry_run?: boolean;
  /** `totals` agrège les compteurs par onglet (`sheets`) : created, updated, skipped, errors. */
  summary: Record<string, unknown> | null;
  created_at?: string;
  finished_at?: string | null;
  reference_date?: string | null;
  created_by_email?: string | null;
  filename?: string;
}

export interface ImportRow {
  id?: string;
  sheet: string;
  row_number: number;
  raw: Record<string, unknown>;
  outcome: 'CREATED' | 'UPDATED' | 'SKIPPED' | 'ERROR' | 'WARNING';
  message: string;
}

export interface DossierImportFile {
  id: string;
  relative_path: string;
  sha256: string;
  content_type: string;
  size_bytes: number;
  extraction: Record<string, unknown>;
  document_id: string | null;
}

export interface DossierImportChange {
  id: string;
  target: string;
  field: string;
  old: unknown;
  new: unknown;
  proof_file_id: string | null;
  confidence: number;
  requires_confirmation: boolean;
}

/** Point à vérifier plus tard prévu par l'analyse (écart scan ≠ fiche, doute de lecture…). */
export interface DossierImportPlannedPoint {
  code: string;
  message: string;
  target: string | null;
  field: string;
  recorded: unknown;
  scan: unknown;
  proof_file_id: string | null;
  confidence: number;
}

/** Seul cas bloquant : l'AMM cible n'est pas identifiable. */
export interface DossierImportQuestion {
  reasons: string[];
  codes: string[];
  /** Le siège peut créer l'AMM absente depuis le dossier (décision d'origine lisible). */
  can_create: boolean;
}

export interface DossierImportPreview {
  version: number;
  /** Fiabilité de la lecture : information de détail, sans effet sur le rangement. */
  confidence: number;
  level: 'HIGH' | 'MEDIUM' | 'LOW';
  can_apply: boolean;
  blockers: string[];
  question?: DossierImportQuestion | null;
  review_points?: DossierImportPlannedPoint[];
  /** AMM choisie à la main en réponse à la question. */
  forced?: boolean;
  warnings: string[];
  amm: {
    id: string | null;
    product_id: string | null;
    product_name: string;
    country_id: string | null;
    country_iso2: string;
    holder: string;
  };
  original: Record<string, unknown>;
  candidates: {
    id: string;
    product_name: string;
    country_iso2: string;
    confidence: number;
    reasons: string[];
  }[];
  documents: {
    file_id: string;
    path: string;
    kind: string;
    /** `original`, clé de renouvellement, ou `unplaced` (période non déterminée). */
    period: string;
    document_date: string | null;
    /** Recueil de décisions : seules ces pages (première, dernière) sont rangées. */
    pages?: [number, number] | null;
    duplicate_id: string | null;
    official?: boolean;
    confidence?: number;
  }[];
  /** Documents communs du dossier pays sans rapport avec ce produit : ni lus ni rangés. */
  ignored?: { file_id: string; path: string; reason: string }[];
  renewals: {
    key: string;
    existing_id: string | null;
    number: string | null;
    start_date: string | null;
    decision_date: string | null;
    end_date: string | null;
    confidence: number;
    proof_file_id: string | null;
  }[];
  changes: DossierImportChange[];
  /** Ce que sera l'AMM une fois rangée (absent des anciens aperçus). */
  projection?: DossierImportProjection | null;
}

export interface DossierImportTimelineStep {
  /** `original`, clé de période du dossier, ou null pour un renouvellement déjà enregistré hors dossier. */
  key: string | null;
  existing_id: string | null;
  number: string;
  start_date: string | null;
  end_date: string | null;
  in_force: boolean;
}

export interface DossierImportProjection {
  effective_end_date: string | null;
  ideal_filing_date: string | null;
  agency_filing_deadline: string | null;
  status: AmmStatus;
  dossier_state: DossierState;
  missing_scan: string | null;
  includes_corrections: boolean;
  timeline: DossierImportTimelineStep[];
}

export interface DossierImportAudit {
  id: string;
  target: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  confidence: number;
  proof_file_id: string | null;
  document_id: string | null;
  user_email: string;
  created_at: string;
  reason: string;
}

export type DossierImportStatus = 'PENDING' | 'RUNNING' | 'READY' | 'QUESTION' | 'APPLIED' | 'FAILED';

/** Point à vérifier plus tard, enregistré sur la fiche AMM : appliquer la valeur du scan ou ignorer. */
export interface DossierReviewPoint {
  id: string;
  batch_id: string;
  batch_name: string;
  amm_id: string;
  renewal_id: string | null;
  code: string;
  field: string;
  message: string;
  recorded_value: unknown;
  scan_value: unknown;
  proof_file_id: string | null;
  proof_name: string | null;
  proof_content_type: string | null;
  confidence: number;
  applicable: boolean;
  status: 'OPEN' | 'APPLIED' | 'IGNORED';
  resolved_by_email: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface DossierImportBatch {
  id: string;
  root_name: string;
  status: DossierImportStatus;
  preview: DossierImportPreview | null;
  preview_token: string;
  created_at: string;
  finished_at: string | null;
  error: string;
  amm_id: string | null;
  files: DossierImportFile[];
  audit: DossierImportAudit[];
  /** Bilan réel après validation ; objet vide tant que l'import n'est pas validé. */
  summary?: DossierImportSummary | Record<string, never>;
  /** Rangé sans intervention dès l'AMM identifiée ; aucune valeur enregistrée remplacée. */
  auto_applied?: boolean;
  review_points?: DossierReviewPoint[];
  open_points_count?: number;
}

/** Récapitulatif des imports (GET /dossier-imports/report) : organisé, corrigé, créé, à traiter. */
export interface DossierReportItem {
  batch_id: string;
  folder: string;
  amm_id: string | null;
  product: string;
  country_iso2: string;
}

export interface DossierReport {
  days: number;
  since: string;
  totals: {
    folders: number;
    filed: number;
    created: number;
    corrected: number;
    completed: number;
    documents: number;
    renewals: number;
    decisions: number;
    attention: number;
    in_progress: number;
  };
  attention: (DossierReportItem & { kind: 'question' | 'failed' | 'ready' | 'incomplete'; reason: string })[];
  created: (DossierReportItem & { number: string })[];
  corrections: (DossierReportItem & { label: string; old: unknown; new: unknown })[];
  decisions: (DossierReportItem & { message: string })[];
  filed: (DossierReportItem & {
    created: boolean;
    documents: number;
    renewals: number;
    completed: number;
    corrected: number;
    status_after: string | null;
    lines: string[];
  })[];
}

export const hasSummary = (summary: DossierImportBatch['summary']): summary is DossierImportSummary =>
  !!summary && 'amm_id' in summary;

export interface DossierImportState {
  status: string;
  dossier_state: string;
  effective_end_date: string | null;
}

export interface DossierImportSummary {
  amm_id: string;
  product: string;
  country: string;
  country_iso2: string;
  number: string;
  created: boolean;
  before: DossierImportState | null;
  after: DossierImportState;
  renewals_created: { number: string; start_date: string | null; end_date: string | null }[];
  fields_changed: { target: 'amm' | 'renewal'; field: string; label: string; old: unknown; new: unknown }[];
  documents: { title: string; kind: string; period: 'original' | 'renewal' }[];
  missing_scan: string | null;
  /** Nombre de points à vérifier plus tard notés au rangement. */
  review_points?: number;
  lines: string[];
}

export type RealtimeEventType =
  | 'amm.updated'
  | 'amm.created'
  | 'renewal.transitioned'
  | 'alert.created'
  | 'alert.updated'
  | 'notification.created'
  | 'document.created'
  | 'dashboard.refresh';

export interface RealtimeEvent {
  type: RealtimeEventType;
  id?: string;
  country?: string;
  amm?: string;
  title?: string;
  body?: string;
}

export type HealthStatus = 'ok' | 'degraded';

/** Réponse de GET /api/v1/health : 200 si la base répond, 503 « degraded » sinon. */
export interface Health {
  status: HealthStatus;
  database: boolean;
  redis: boolean;
  /** APP_VERSION côté API (« dev » par défaut) ; '' si l'API ne l'expose pas encore. */
  version: string;
}
