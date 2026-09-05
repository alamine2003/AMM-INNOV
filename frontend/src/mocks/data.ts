import type {
  Alert,
  AlertRule,
  Amm,
  AmmDocument,
  AmmStatus,
  Country,
  DossierState,
  HistoryEntry,
  ImportBatch,
  ImportRow,
  Notification,
  Product,
  ProductRange,
  Renewal,
  Urgency,
  User,
  WorkflowStatus,
} from '@/api/types';
import { addDays, addMonths, addYears, differenceInCalendarMonths, format, parseISO } from 'date-fns';

export const MOCK_TODAY = '2026-09-04';
const today = parseISO(MOCK_TODAY);
const iso = (d: Date) => format(d, 'yyyy-MM-dd');
const shift = (days: number) => iso(addDays(today, days));

export const MOCK_PASSWORD = 'Passw0rd!';

export const countries: Country[] = [
  {
    id: 'c-sn',
    iso2: 'SN',
    name: 'Sénégal',
    authority: 'DPM / ARP',
    validity_years: 5,
    filing_lead_months: 6,
    timezone: 'Africa/Dakar',
  },
  {
    id: 'c-ci',
    iso2: 'CI',
    name: "Côte d'Ivoire",
    authority: 'AIRP',
    validity_years: 5,
    filing_lead_months: 6,
    timezone: 'Africa/Abidjan',
  },
  {
    id: 'c-cm',
    iso2: 'CM',
    name: 'Cameroun',
    authority: 'DPML',
    validity_years: 5,
    filing_lead_months: 6,
    timezone: 'Africa/Douala',
  },
];

export const ranges: ProductRange[] = [
  { id: 'r-gen', code: 'GENERALE', label: 'Générale' },
  { id: 'r-car', code: 'CARDIO', label: 'Cardio' },
  { id: 'r-be', code: 'BIEN_ETRE', label: 'Bien-être' },
];

export const products: Product[] = [
  {
    id: 'p-1',
    name: 'AMOXICILLINE 500 MG GEL B/12',
    range: 'r-gen',
    range_code: 'GENERALE',
    dci: 'Amoxicilline',
    dosage: '500 mg',
    form: 'Gélule',
    presentation: 'B/12',
    is_active: true,
    aliases: ['AMOXICILINE 500MG B12'],
  },
  {
    id: 'p-2',
    name: 'PARACETAMOL 1 G CP B/8',
    range: 'r-gen',
    range_code: 'GENERALE',
    dci: 'Paracétamol',
    dosage: '1 g',
    form: 'Comprimé',
    presentation: 'B/8',
    is_active: true,
    aliases: [],
  },
  {
    id: 'p-3',
    name: 'AMLODIPINE 10 MG CP B/30',
    range: 'r-car',
    range_code: 'CARDIO',
    dci: 'Amlodipine',
    dosage: '10 mg',
    form: 'Comprimé',
    presentation: 'B/30',
    is_active: true,
    aliases: ['AMLODIPINE 10MG B30'],
  },
  {
    id: 'p-4',
    name: 'ATORVASTATINE 20 MG CP B/30',
    range: 'r-car',
    range_code: 'CARDIO',
    dci: 'Atorvastatine',
    dosage: '20 mg',
    form: 'Comprimé',
    presentation: 'B/30',
    is_active: true,
    aliases: [],
  },
  {
    id: 'p-5',
    name: 'VITAMINE C 500 MG CP B/20',
    range: 'r-be',
    range_code: 'BIEN_ETRE',
    dci: 'Acide ascorbique',
    dosage: '500 mg',
    form: 'Comprimé',
    presentation: 'B/20',
    is_active: true,
    aliases: ['VIT C 500'],
  },
  {
    id: 'p-6',
    name: 'METFORMINE 850 MG CP B/30',
    range: 'r-gen',
    range_code: 'GENERALE',
    dci: 'Metformine',
    dosage: '850 mg',
    form: 'Comprimé',
    presentation: 'B/30',
    is_active: true,
    aliases: [],
  },
];

export const users: User[] = [
  {
    id: 'u-ceo',
    email: 'ceo@amm-innov.test',
    first_name: 'Awa',
    last_name: 'Diop',
    role: 'CEO_ADMIN',
    countries: [],
    is_active: true,
  },
  {
    id: 'u-hq',
    email: 'siege@amm-innov.test',
    first_name: 'Moussa',
    last_name: 'Ndiaye',
    role: 'HQ_REGULATORY',
    countries: [],
    is_active: true,
  },
  {
    id: 'u-sn',
    email: 'senegal@amm-innov.test',
    first_name: 'Fatou',
    last_name: 'Sarr',
    role: 'COUNTRY_REGULATORY',
    countries: ['SN'],
    is_active: true,
  },
  {
    id: 'u-ci',
    email: 'ci@amm-innov.test',
    first_name: 'Koffi',
    last_name: 'Kouassi',
    role: 'COUNTRY_REGULATORY',
    countries: ['CI', 'CM'],
    is_active: true,
  },
];

interface AmmSeed {
  id: string;
  product: string;
  country: string;
  original_number: string | null;
  original_start_date: string | null;
  dossier_state: DossierState;
  renewals?: {
    workflow_status: WorkflowStatus;
    filing_date?: string;
    number?: string;
    start_date?: string;
  }[];
  notes?: string;
}

const seeds: AmmSeed[] = [
  // SN
  {
    id: 'amm-1',
    product: 'p-1',
    country: 'SN',
    original_number: 'SN-2019-0412',
    original_start_date: '2019-03-12',
    dossier_state: 'COMPLET',
    renewals: [
      {
        workflow_status: 'OBTENU',
        filing_date: '2023-09-01',
        number: 'SN-2024-0102',
        start_date: '2024-03-12',
      },
    ],
  },
  {
    id: 'amm-2',
    product: 'p-2',
    country: 'SN',
    original_number: 'SN-2021-0888',
    original_start_date: shift(-365 * 5 + 120),
    dossier_state: 'INCOMPLET',
  },
  {
    id: 'amm-3',
    product: 'p-3',
    country: 'SN',
    original_number: 'SN-2021-0910',
    original_start_date: shift(-365 * 5 + 45),
    dossier_state: 'COMPLET',
  },
  {
    id: 'amm-4',
    product: 'p-5',
    country: 'SN',
    original_number: 'SN-2018-0021',
    original_start_date: '2018-01-15',
    dossier_state: 'INCOMPLET',
    notes: 'Renouvellement à relancer',
  },
  // CI
  {
    id: 'amm-5',
    product: 'p-1',
    country: 'CI',
    original_number: 'CI-2020-1147',
    original_start_date: shift(-365 * 5 + 100),
    dossier_state: 'COMPLET',
    renewals: [{ workflow_status: 'DEPOSE', filing_date: shift(-40) }],
  },
  {
    id: 'amm-6',
    product: 'p-4',
    country: 'CI',
    original_number: 'CI-2023-0330',
    original_start_date: '2023-06-01',
    dossier_state: 'COMPLET',
  },
  {
    id: 'amm-7',
    product: 'p-6',
    country: 'CI',
    original_number: 'CI-2022-0777',
    original_start_date: shift(-365 * 5 + 300),
    dossier_state: 'INCOMPLET',
  },
  // CM
  {
    id: 'amm-8',
    product: 'p-3',
    country: 'CM',
    original_number: '2021179002',
    original_start_date: '2021-07-20',
    dossier_state: 'COMPLET',
  },
  {
    id: 'amm-9',
    product: 'p-2',
    country: 'CM',
    original_number: null,
    original_start_date: null,
    dossier_state: 'INCONNU',
    notes: 'DATE ILLISIBLE — A RESSAISIR',
  },
  {
    id: 'amm-10',
    product: 'p-5',
    country: 'CM',
    original_number: 'CM-2020-0555',
    original_start_date: shift(-365 * 5 + 20),
    dossier_state: 'INCOMPLET',
    renewals: [{ workflow_status: 'EN_PREPARATION' }],
  },
];

export interface MockDb {
  countries: Country[];
  ranges: ProductRange[];
  products: Product[];
  users: User[];
  amms: Amm[];
  renewals: Renewal[];
  documents: AmmDocument[];
  alerts: Alert[];
  alertRules: AlertRule[];
  notifications: Notification[];
  history: Record<string, HistoryEntry[]>;
  imports: ImportBatch[];
  importRows: Record<string, ImportRow[]>;
  /** Utilisateur dont le cookie de session (refresh httpOnly) est valide. */
  session: string | null;
}

function computeState(amm: Amm, renewals: Renewal[], country: Country) {
  const last = [...renewals]
    .filter((r) => r.workflow_status === 'OBTENU')
    .sort((a, b) => b.sequence - a.sequence)[0];
  const pending = renewals.some(
    (r) => r.workflow_status === 'DEPOSE' || r.workflow_status === 'EN_INSTRUCTION',
  );
  let end: string | null = null;
  if (last?.end_date) end = last.end_date;
  else if (amm.original_end_date) end = amm.original_end_date;
  let status: AmmStatus;
  if (!end) status = pending ? 'IN_PROCESS' : 'INDETERMINE';
  else if (end >= MOCK_TODAY) status = 'VALIDE';
  else status = pending ? 'IN_PROCESS' : 'EXPIRE';
  const deadline = end ? iso(addMonths(parseISO(end), -country.filing_lead_months)) : null;
  let urgency: Urgency;
  if (pending) urgency = 'EN_INSTRUCTION';
  else if (!end) urgency = 'A_PLANIFIER';
  else {
    const months = differenceInCalendarMonths(parseISO(end), today);
    if (end < MOCK_TODAY) urgency = 'EXPIRE';
    else if (months <= 3) urgency = 'CRITIQUE';
    else if (months <= 6) urgency = 'DEPOT_URGENT';
    else if (months <= 12) urgency = 'A_PLANIFIER';
    else urgency = 'OK';
  }
  return { status, urgency, effective_end_date: end, filing_deadline: deadline };
}

export function recomputeAmm(db: MockDb, ammId: string) {
  const amm = db.amms.find((a) => a.id === ammId);
  if (!amm) return;
  const country = db.countries.find((c) => c.iso2 === amm.country_iso2)!;
  const renewals = db.renewals.filter((r) => r.amm_id === ammId);
  if (amm.original_start_date && !amm.original_end_date_manual) {
    amm.original_end_date = iso(addYears(parseISO(amm.original_start_date), country.validity_years));
  }
  for (const r of renewals) {
    if (r.start_date && !r.end_date_manual)
      r.end_date = iso(addYears(parseISO(r.start_date), country.validity_years));
  }
  const state = computeState(amm, renewals, country);
  Object.assign(amm, state);
  const current = [...renewals].sort((a, b) => b.sequence - a.sequence)[0];
  amm.last_renewal = current
    ? {
        id: current.id,
        sequence: current.sequence,
        workflow_status: current.workflow_status,
        number: current.number,
        start_date: current.start_date,
        end_date: current.end_date,
      }
    : null;
  const currentDocs = db.documents.filter(
    (d) => d.amm === ammId && d.is_current && !d.archived_at && d.kind === 'AMM',
  );
  const obtained = [...renewals]
    .filter((r) => r.workflow_status === 'OBTENU')
    .sort((a, b) => b.sequence - a.sequence)[0];
  amm.has_current_scan = obtained
    ? currentDocs.some((d) => d.renewal === obtained.id)
    : currentDocs.some((d) => d.renewal === null);
  amm.updated_at = new Date().toISOString();
}

export function buildDb(): MockDb {
  const db: MockDb = {
    session: null,
    countries: structuredClone(countries),
    ranges: structuredClone(ranges),
    products: structuredClone(products),
    users: structuredClone(users),
    amms: [],
    renewals: [],
    documents: [],
    alerts: [],
    alertRules: [],
    notifications: [],
    history: {},
    imports: [],
    importRows: {},
  };

  for (const seed of seeds) {
    const product = db.products.find((p) => p.id === seed.product)!;
    const country = db.countries.find((c) => c.iso2 === seed.country)!;
    const amm: Amm = {
      id: seed.id,
      product: product.id,
      product_name: product.name,
      range_code: product.range_code,
      country: country.id,
      country_iso2: country.iso2,
      country_name: country.name,
      original_number: seed.original_number,
      original_start_date: seed.original_start_date,
      original_end_date: null,
      original_end_date_manual: false,
      status: 'INDETERMINE',
      urgency: 'A_PLANIFIER',
      effective_end_date: null,
      filing_deadline: null,
      dossier_state: seed.dossier_state,
      notes: seed.notes ?? '',
      owner: null,
      has_current_scan: false,
      last_renewal: null,
      updated_at: '2026-08-18T10:00:00Z',
    };
    db.amms.push(amm);
    (seed.renewals ?? []).forEach((r, i) => {
      db.renewals.push({
        id: `${seed.id}-ren-${i + 1}`,
        amm_id: seed.id,
        sequence: i + 1,
        workflow_status: r.workflow_status,
        filing_date: r.filing_date ?? null,
        decision_date: r.workflow_status === 'OBTENU' ? (r.start_date ?? null) : null,
        number: r.number ?? null,
        start_date: r.start_date ?? null,
        end_date: null,
        end_date_manual: false,
        notes: '',
        created_at: '2026-01-10T09:00:00Z',
      });
    });
    db.history[seed.id] = [
      {
        date: '2026-08-18T10:00:00Z',
        user_email: 'siege@amm-innov.test',
        type: 'IMPORT',
        changes: [{ field: 'original_number', old: null, new: seed.original_number }],
      },
    ];
  }

  // Documents : amm-1 possède l'AMM d'origine + renouvellement obtenu (en vigueur) + récépissé.
  const docBase = (
    id: string,
    amm: string,
    renewal: string | null,
    kind: AmmDocument['kind'],
    date: string,
    title: string,
    uploaded: string,
    extra: Partial<AmmDocument> = {},
  ): AmmDocument => ({
    id,
    amm,
    amm_id: amm,
    renewal,
    renewal_id: renewal,
    renewal_sequence: renewal ? (db.renewals.find((r) => r.id === renewal)?.sequence ?? null) : null,
    country_iso2: db.amms.find((a) => a.id === amm)?.country_iso2 ?? '',
    product_name: db.amms.find((a) => a.id === amm)?.product_name ?? '',
    kind,
    title,
    document_date: date,
    sha256: `sha-${id}`,
    size_bytes: 1_240_000,
    page_count: 2,
    version: 1,
    replaces: null,
    is_current: true,
    uploaded_by_email: 'senegal@amm-innov.test',
    uploaded_at: uploaded,
    archived_at: null,
    file_url: `/api/v1/documents/${id}/file`,
    ...extra,
  });
  db.documents.push(
    docBase(
      'doc-1',
      'amm-1',
      'amm-1-ren-1',
      'AMM',
      '2024-03-12',
      'AMM renouvelée 2024',
      '2024-04-02T09:00:00Z',
    ),
    docBase(
      'doc-2',
      'amm-1',
      'amm-1-ren-1',
      'RECEPISSE',
      '2023-09-01',
      'Récépissé de dépôt',
      '2023-09-03T09:00:00Z',
    ),
    docBase('doc-3', 'amm-1', null, 'AMM', '2019-03-12', 'AMM initiale 2019', '2021-01-15T09:00:00Z'),
    docBase('doc-4', 'amm-3', null, 'AMM', '2021-10-20', 'AMM initiale', '2022-02-01T09:00:00Z'),
    docBase('doc-5', 'amm-6', null, 'AMM', '2023-06-01', 'AMM initiale', '2023-07-10T09:00:00Z'),
    docBase(
      'doc-6',
      'amm-5',
      'amm-5-ren-1',
      'RECEPISSE',
      shift(-40),
      'Récépissé AIRP',
      new Date(addDays(today, -39)).toISOString(),
    ),
    docBase('doc-7', 'amm-8', null, 'AMM', '2021-07-20', 'AMM DPML', '2021-09-01T09:00:00Z'),
  );

  for (const a of db.amms) recomputeAmm(db, a.id);

  db.alertRules = [
    {
      id: 'rule-365',
      code: 'J-365',
      country: null,
      offset_days: 365,
      severity: 'INFO',
      roles: ['COUNTRY_REGULATORY'],
      channels: ['in_app'],
      only_if_not_filed: true,
      is_active: true,
    },
    {
      id: 'rule-180',
      code: 'J-180',
      country: null,
      offset_days: 180,
      severity: 'WARNING',
      roles: ['COUNTRY_REGULATORY', 'HQ_REGULATORY'],
      channels: ['in_app', 'email'],
      only_if_not_filed: true,
      is_active: true,
    },
    {
      id: 'rule-90',
      code: 'J-90',
      country: null,
      offset_days: 90,
      severity: 'CRITICAL',
      roles: ['COUNTRY_REGULATORY', 'HQ_REGULATORY'],
      channels: ['in_app', 'email'],
      only_if_not_filed: true,
      is_active: true,
    },
    {
      id: 'rule-30',
      code: 'J-30',
      country: null,
      offset_days: 30,
      severity: 'CRITICAL',
      roles: ['COUNTRY_REGULATORY', 'HQ_REGULATORY', 'CEO_ADMIN'],
      channels: ['in_app', 'email'],
      only_if_not_filed: true,
      is_active: true,
    },
    {
      id: 'rule-0',
      code: 'J0',
      country: null,
      offset_days: 0,
      severity: 'CRITICAL',
      roles: ['COUNTRY_REGULATORY', 'HQ_REGULATORY', 'CEO_ADMIN'],
      channels: ['in_app', 'email'],
      only_if_not_filed: false,
      is_active: true,
    },
    {
      id: 'rule-dec',
      code: 'DECISION',
      country: null,
      offset_days: 120,
      severity: 'WARNING',
      roles: ['COUNTRY_REGULATORY'],
      channels: ['in_app'],
      only_if_not_filed: false,
      is_active: true,
    },
    {
      id: 'rule-dos',
      code: 'DOSSIER',
      country: null,
      offset_days: 270,
      severity: 'INFO',
      roles: ['COUNTRY_REGULATORY'],
      channels: ['in_app'],
      only_if_not_filed: false,
      is_active: true,
    },
  ];

  const mkAlert = (
    id: string,
    ammId: string,
    rule: string,
    severity: Alert['severity'],
    status: Alert['status'],
    extra: Partial<Alert> = {},
  ): Alert => {
    const amm = db.amms.find((a) => a.id === ammId)!;
    return {
      id,
      amm: ammId,
      amm_id: ammId,
      product_name: amm.product_name,
      country_iso2: amm.country_iso2,
      country_name: amm.country_name,
      amm_status: amm.status,
      amm_urgency: amm.urgency,
      effective_end_date: amm.effective_end_date,
      rule_code: rule,
      severity,
      due_date: amm.filing_deadline ?? MOCK_TODAY,
      status,
      assigned_to: null,
      assigned_to_email: null,
      triggered_at: '2026-09-01T00:15:00Z',
      acknowledged_at: null,
      resolved_at: null,
      resolution: null,
      comment: null,
      ...extra,
    };
  };
  db.alerts = [
    mkAlert('al-1', 'amm-3', 'J-90', 'CRITICAL', 'OPEN'),
    mkAlert('al-2', 'amm-2', 'J-180', 'WARNING', 'OPEN'),
    mkAlert('al-3', 'amm-10', 'J-30', 'CRITICAL', 'ACKNOWLEDGED', {
      acknowledged_at: '2026-09-02T08:00:00Z',
      assigned_to: 'u-ci',
      assigned_to_email: 'ci@amm-innov.test',
    }),
    mkAlert('al-4', 'amm-4', 'J0', 'CRITICAL', 'OPEN'),
    mkAlert('al-5', 'amm-7', 'J-365', 'INFO', 'OPEN'),
    mkAlert('al-6', 'amm-5', 'J-180', 'WARNING', 'RESOLVED', {
      resolved_at: shift(-40),
      resolution: 'AUTO_FILED',
    }),
    mkAlert('al-7', 'amm-2', 'DOSSIER', 'INFO', 'OPEN'),
  ];

  db.notifications = [
    {
      id: 'n-1',
      title: 'Alerte J-90 — AMLODIPINE 10 MG CP B/30 (SN)',
      body: 'Dépôt urgent : expiration dans moins de 3 mois.',
      link: '/amms/amm-3',
      channel: 'IN_APP',
      sent_at: '2026-09-01T00:16:00Z',
      read_at: null,
    },
    {
      id: 'n-2',
      title: 'Alerte J-180 — PARACETAMOL 1 G CP B/8 (SN)',
      body: 'Deadline de dépôt atteinte.',
      link: '/amms/amm-2',
      channel: 'IN_APP',
      sent_at: '2026-09-01T00:16:00Z',
      read_at: null,
    },
    {
      id: 'n-3',
      title: 'Alerte J0 — VITAMINE C 500 MG CP B/20 (SN)',
      body: 'AMM expirée.',
      link: '/amms/amm-4',
      channel: 'IN_APP',
      sent_at: '2026-08-30T00:16:00Z',
      read_at: null,
    },
    {
      id: 'n-4',
      title: 'Import terminé',
      body: 'Classeur importé : 10 lignes.',
      link: '/admin/imports/imp-1',
      channel: 'IN_APP',
      sent_at: '2026-08-18T10:05:00Z',
      read_at: '2026-08-18T11:00:00Z',
    },
  ];

  db.imports = [
    {
      id: 'imp-1',
      status: 'DONE',
      summary: {
        totals: { created: 10, updated: 0, skipped: 2, errors: 2, warnings: 1 },
        sheets: {
          SENEGAL: { created: 4, errors: 0 },
          CDI: { created: 3, errors: 1 },
          CAMEROUN: { created: 3, errors: 1 },
        },
      },
      created_at: '2026-08-18T10:00:00Z',
      filename: 'Dashboard AMM Afrique 18_08_2026 version 2.1.xlsx',
    },
  ];
  db.importRows['imp-1'] = [
    {
      sheet: 'CAMEROUN',
      row_number: 14,
      raw: {
        GAMME: 'GAMME GENERAL',
        NOM: 'PARACETAMOL 1 G CP B/8',
        'DATE DEBUT': 'DATE ILLISIBLE — A RESSAISIR',
      },
      outcome: 'ERROR',
      message: 'Date de début illisible',
    },
    {
      sheet: 'CDI',
      row_number: 27,
      raw: { GAMME: 'GAME CARDIO', NOM: 'ATORVASTATINE 20MG', 'N° AMM': '' },
      outcome: 'ERROR',
      message: 'Numéro d’AMM manquant',
    },
    {
      sheet: 'SENEGAL',
      row_number: 3,
      raw: { NOM: 'AMOXICILINE 500MG B12' },
      outcome: 'CREATED',
      message: '',
    },
  ];

  return db;
}

export const SAMPLE_PDF = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 60 >> stream
BT /F1 24 Tf 72 760 Td (AMM INNOV - document de demonstration) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
trailer << /Root 1 0 R /Size 6 >>
startxref
0
%%EOF`;
