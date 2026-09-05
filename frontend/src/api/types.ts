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
  refresh: string;
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
  filing_lead_months: number;
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
  range: string;
  range_code: string;
  dci: string;
  dosage: string;
  form: string;
  presentation: string;
  is_active: boolean;
  aliases: string[];
}

export type AmmStatus = 'VALIDE' | 'EXPIRE' | 'IN_PROCESS' | 'INDETERMINE';
export type Urgency = 'OK' | 'A_PLANIFIER' | 'DEPOT_URGENT' | 'CRITIQUE' | 'EXPIRE' | 'EN_INSTRUCTION';
export type DossierState = 'COMPLET' | 'INCOMPLET' | 'INCONNU';
export type WorkflowStatus =
  'PLANIFIE' | 'EN_PREPARATION' | 'DEPOSE' | 'EN_INSTRUCTION' | 'OBTENU' | 'REJETE' | 'ABANDONNE';

export interface CurrentRenewal {
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
  original_number: string | null;
  original_start_date: string | null;
  original_end_date: string | null;
  original_end_date_manual: boolean;
  status: AmmStatus;
  urgency: Urgency;
  effective_end_date: string | null;
  filing_deadline: string | null;
  dossier_state: DossierState;
  notes: string;
  owner: string | null;
  has_current_scan: boolean;
  current_renewal: CurrentRenewal | null;
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
  user_email: string;
  type: string;
  changes: HistoryChange[];
}

export interface Renewal {
  id: string;
  amm: string;
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
  filing_date?: string | null;
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
  sent_at: string;
  read_at: string | null;
}

export interface AfricaRow {
  country_iso2: string;
  country_name: string;
  total: number;
  valid: number;
  expired: number;
  in_process: number;
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
  outcome: 'CREATED' | 'UPDATED' | 'SKIPPED' | 'ERROR';
  message: string;
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
