import { http, HttpResponse, delay } from 'msw';
import type {
  AfricaRow,
  AlertRule,
  Amm,
  AmmDocument,
  Country,
  DocumentPeriod,
  Product,
  ProductRange,
  Renewal,
  User,
  WorkflowStatus,
} from '@/api/types';
import { buildDb, MOCK_PASSWORD, MOCK_TODAY, recomputeAmm, SAMPLE_PDF, type MockDb } from './data';
import { addMonths, differenceInCalendarMonths, format, parseISO } from 'date-fns';

export let db: MockDb = buildDb();
export function resetDb() {
  db = buildDb();
}

const BASE = '/api/v1';
const url = (path: string) => `${BASE}${path}`;
let idCounter = 1000;
const nextId = (prefix: string) => `${prefix}-${++idCounter}`;

/** Jeton mock : `mock-access-<userId>` / `mock-refresh-<userId>`. */
const ACCESS_PREFIX = 'mock-access-';
const REFRESH_PREFIX = 'mock-refresh-';
export const EXPIRED_ACCESS = 'mock-access-expired';

function currentUser(request: Request): User | null {
  const header = request.headers.get('authorization') ?? '';
  const token = header.replace(/^Bearer\s+/i, '');
  if (!token.startsWith(ACCESS_PREFIX) || token === EXPIRED_ACCESS) return null;
  const id = token.slice(ACCESS_PREFIX.length);
  return db.users.find((u) => u.id === id) ?? null;
}

function unauthorized() {
  return HttpResponse.json({ detail: 'Authentification requise' }, { status: 401 });
}

function forbidden() {
  return HttpResponse.json({ detail: 'Accès refusé' }, { status: 403 });
}

function inScope(user: User, iso2: string) {
  return user.role !== 'COUNTRY_REGULATORY' || user.countries.includes(iso2);
}

function scopedAmms(user: User): Amm[] {
  return db.amms.filter((a) => inScope(user, a.country_iso2));
}

function paginate<T>(items: T[], request: Request) {
  const sp = new URL(request.url).searchParams;
  const page = Number(sp.get('page') ?? 1);
  const pageSize = Number(sp.get('page_size') ?? 50);
  const start = (page - 1) * pageSize;
  return {
    count: items.length,
    next: start + pageSize < items.length ? `?page=${page + 1}` : null,
    previous: page > 1 ? `?page=${page - 1}` : null,
    results: items.slice(start, start + pageSize),
  };
}

type HandlerInfo = { request: Request; params: Record<string, string | readonly string[] | undefined> };

function withAuth(handler: (user: User, info: HandlerInfo) => Response | Promise<Response>) {
  return async (info: HandlerInfo) => {
    const user = currentUser(info.request);
    if (!user) return unauthorized();
    return handler(user, info);
  };
}

function sortDocs(docs: AmmDocument[]) {
  return [...docs].sort(
    (a, b) => b.document_date.localeCompare(a.document_date) || b.uploaded_at.localeCompare(a.uploaded_at),
  );
}

function addHistory(
  ammId: string,
  user: User,
  type: string,
  changes: { field: string; old: unknown; new: unknown }[],
) {
  db.history[ammId] = [
    { date: new Date().toISOString(), user_email: user.email, type, changes },
    ...(db.history[ammId] ?? []),
  ];
}

function africaRows(user: User): { rows: AfricaRow[]; total: AfricaRow } {
  const amms = scopedAmms(user);
  const today = parseISO(MOCK_TODAY);
  const in6 = format(addMonths(today, 6), 'yyyy-MM-dd');
  const in12 = format(addMonths(today, 12), 'yyyy-MM-dd');
  const rowFor = (iso2: string, name: string, list: Amm[]): AfricaRow => {
    const total = list.length;
    const valid = list.filter((a) => a.status === 'VALIDE').length;
    const complete = list.filter((a) => a.dossier_state === 'COMPLET').length;
    const exp = (limit: string) =>
      list.filter(
        (a) => a.effective_end_date && a.effective_end_date >= MOCK_TODAY && a.effective_end_date <= limit,
      ).length;
    return {
      country_iso2: iso2,
      country_name: name,
      total,
      valid,
      expired: list.filter((a) => a.status === 'EXPIRE').length,
      in_process: list.filter((a) => a.status === 'IN_PROCESS').length,
      undetermined: list.filter((a) => a.status === 'INDETERMINE').length,
      pct_valid: total ? Math.round((valid / total) * 100) : 0,
      expiring_6m: exp(in6),
      expiring_12m: exp(in12),
      pct_complete: total ? Math.round((complete / total) * 100) : 0,
    };
  };
  const countries = db.countries.filter((c) => inScope(user, c.iso2));
  const rows = countries.map((c) =>
    rowFor(
      c.iso2,
      c.name,
      amms.filter((a) => a.country_iso2 === c.iso2),
    ),
  );
  return { rows, total: rowFor('ALL', 'TOTAL', amms) };
}

const TRANSITIONS: Record<WorkflowStatus, WorkflowStatus[]> = {
  PLANIFIE: ['EN_PREPARATION', 'ABANDONNE'],
  EN_PREPARATION: ['DEPOSE', 'ABANDONNE'],
  DEPOSE: ['EN_INSTRUCTION', 'OBTENU', 'ABANDONNE'],
  EN_INSTRUCTION: ['OBTENU', 'REJETE', 'ABANDONNE'],
  OBTENU: [],
  REJETE: [],
  ABANDONNE: [],
};

async function readForm(request: Request) {
  const form = await request.formData();
  const file = form.get('file');
  return { form, file: file instanceof File ? file : null };
}

export const handlers = [
  // ---- Auth ----
  http.post(url('/auth/login'), async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    const user = db.users.find((u) => u.email.toLowerCase() === body.email?.toLowerCase());
    if (!user || body.password !== MOCK_PASSWORD) {
      return HttpResponse.json({ detail: 'Identifiants incorrects' }, { status: 401 });
    }
    return HttpResponse.json({
      access: `${ACCESS_PREFIX}${user.id}`,
      refresh: `${REFRESH_PREFIX}${user.id}`,
      user,
    });
  }),
  http.post(url('/auth/refresh'), async ({ request }) => {
    const body = (await request.json()) as { refresh: string };
    if (!body.refresh?.startsWith(REFRESH_PREFIX)) return unauthorized();
    const id = body.refresh.slice(REFRESH_PREFIX.length);
    if (!db.users.some((u) => u.id === id)) return unauthorized();
    return HttpResponse.json({ access: `${ACCESS_PREFIX}${id}` });
  }),
  http.post(url('/auth/logout'), () => new HttpResponse(null, { status: 204 })),
  http.get(
    url('/me'),
    withAuth((user) => HttpResponse.json(user)),
  ),
  http.get(url('/health'), () => HttpResponse.json({ status: 'ok' })),

  // ---- Référentiels ----
  http.get(
    url('/countries'),
    withAuth((_u, { request }) => HttpResponse.json(paginate(db.countries, request))),
  ),
  http.post(
    url('/countries'),
    withAuth(async (_u, { request }) => {
      const body = (await request.json()) as Partial<Country>;
      const c: Country = {
        id: nextId('c'),
        iso2: '',
        name: '',
        authority: '',
        validity_years: 5,
        filing_lead_months: 6,
        timezone: 'Africa/Dakar',
        ...body,
      };
      db.countries.push(c);
      return HttpResponse.json(c, { status: 201 });
    }),
  ),
  http.patch(
    url('/countries/:id'),
    withAuth(async (_u, { request, params }) => {
      const c = db.countries.find((x) => x.id === params.id);
      if (!c) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      Object.assign(c, await request.json());
      return HttpResponse.json(c);
    }),
  ),
  http.delete(
    url('/countries/:id'),
    withAuth((_u, { params }) => {
      db.countries = db.countries.filter((x) => x.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  ),
  http.get(
    url('/countries/:iso2/documents'),
    withAuth((user, { request, params }) => {
      const iso2 = String(params.iso2);
      if (!inScope(user, iso2)) return forbidden();
      const sp = new URL(request.url).searchParams;
      const kind = sp.get('kind');
      const year = sp.get('year');
      const ammIds = db.amms.filter((a) => a.country_iso2 === iso2);
      let docs = db.documents.filter(
        (d) => d.is_current && !d.archived_at && ammIds.some((a) => a.id === d.amm),
      );
      if (kind) docs = docs.filter((d) => d.kind === kind);
      if (year) docs = docs.filter((d) => d.document_date.startsWith(year));
      const enriched = sortDocs(docs).map((d) => {
        const amm = db.amms.find((a) => a.id === d.amm)!;
        return {
          ...d,
          amm_summary: {
            id: amm.id,
            product_name: amm.product_name,
            country_iso2: amm.country_iso2,
            country_name: amm.country_name,
          },
        };
      });
      return HttpResponse.json(paginate(enriched, request));
    }),
  ),

  http.get(
    url('/ranges'),
    withAuth((_u, { request }) => HttpResponse.json(paginate(db.ranges, request))),
  ),
  http.post(
    url('/ranges'),
    withAuth(async (_u, { request }) => {
      const body = (await request.json()) as Partial<ProductRange>;
      const r: ProductRange = { id: nextId('r'), code: '', label: '', ...body };
      db.ranges.push(r);
      return HttpResponse.json(r, { status: 201 });
    }),
  ),
  http.patch(
    url('/ranges/:id'),
    withAuth(async (_u, { request, params }) => {
      const r = db.ranges.find((x) => x.id === params.id);
      if (!r) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      Object.assign(r, await request.json());
      return HttpResponse.json(r);
    }),
  ),
  http.delete(
    url('/ranges/:id'),
    withAuth((_u, { params }) => {
      db.ranges = db.ranges.filter((x) => x.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  ),

  http.get(
    url('/products'),
    withAuth((_u, { request }) => {
      const search = new URL(request.url).searchParams.get('search')?.toLowerCase();
      const list = search
        ? db.products.filter(
            (p) =>
              p.name.toLowerCase().includes(search) ||
              p.aliases.some((a) => a.toLowerCase().includes(search)),
          )
        : db.products;
      return HttpResponse.json(paginate(list, request));
    }),
  ),
  http.get(
    url('/products/:id'),
    withAuth((_u, { params }) => {
      const p = db.products.find((x) => x.id === params.id);
      return p ? HttpResponse.json(p) : HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
    }),
  ),
  http.post(
    url('/products'),
    withAuth(async (_u, { request }) => {
      const body = (await request.json()) as Partial<Product>;
      const range = db.ranges.find((r) => r.id === body.range);
      const p: Product = {
        id: nextId('p'),
        name: '',
        range: '',
        range_code: range?.code ?? '',
        dci: '',
        dosage: '',
        form: '',
        presentation: '',
        is_active: true,
        aliases: [],
        ...body,
      };
      db.products.push(p);
      return HttpResponse.json(p, { status: 201 });
    }),
  ),
  http.patch(
    url('/products/:id'),
    withAuth(async (_u, { request, params }) => {
      const p = db.products.find((x) => x.id === params.id);
      if (!p) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      Object.assign(p, await request.json());
      p.range_code = db.ranges.find((r) => r.id === p.range)?.code ?? p.range_code;
      return HttpResponse.json(p);
    }),
  ),
  http.delete(
    url('/products/:id'),
    withAuth((_u, { params }) => {
      db.products = db.products.filter((x) => x.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  ),
  http.post(
    url('/products/:id/merge'),
    withAuth(async (_u, { request, params }) => {
      const body = (await request.json()) as { target_id: string };
      const source = db.products.find((x) => x.id === params.id);
      const target = db.products.find((x) => x.id === body.target_id);
      if (!source || !target) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      target.aliases = [...target.aliases, source.name, ...source.aliases];
      for (const a of db.amms)
        if (a.product === source.id) {
          a.product = target.id;
          a.product_name = target.name;
          a.range_code = target.range_code;
        }
      db.products = db.products.filter((x) => x.id !== source.id);
      return HttpResponse.json(target);
    }),
  ),
  http.get(
    url('/products/:id/documents'),
    withAuth((user, { request, params }) => {
      const amms = scopedAmms(user).filter((a) => a.product === params.id);
      const docs = db.documents.filter(
        (d) => d.is_current && !d.archived_at && amms.some((a) => a.id === d.amm),
      );
      const enriched = sortDocs(docs).map((d) => {
        const amm = db.amms.find((a) => a.id === d.amm)!;
        return {
          ...d,
          amm_summary: {
            id: amm.id,
            product_name: amm.product_name,
            country_iso2: amm.country_iso2,
            country_name: amm.country_name,
          },
        };
      });
      return HttpResponse.json(paginate(enriched, request));
    }),
  ),

  // ---- AMM ----
  http.get(
    url('/amms'),
    withAuth((user, { request }) => {
      const sp = new URL(request.url).searchParams;
      let list = scopedAmms(user);
      const eq = (key: string, field: keyof Amm) => {
        const v = sp.get(key);
        if (v) list = list.filter((a) => String(a[field]) === v);
      };
      const country = sp.get('country');
      if (country) list = list.filter((a) => a.country_iso2 === country || a.country === country);
      const range = sp.get('range');
      if (range)
        list = list.filter(
          (a) => a.range_code === range || db.ranges.find((r) => r.id === range)?.code === a.range_code,
        );
      eq('status', 'status');
      eq('urgency', 'urgency');
      eq('dossier_state', 'dossier_state');
      const scan = sp.get('has_current_scan');
      if (scan) list = list.filter((a) => a.has_current_scan === (scan === 'true'));
      const expiresBefore = sp.get('expires_before');
      if (expiresBefore)
        list = list.filter((a) => a.effective_end_date && a.effective_end_date <= expiresBefore);
      const search = sp.get('search')?.toLowerCase();
      if (search)
        list = list.filter(
          (a) =>
            a.product_name.toLowerCase().includes(search) ||
            (a.original_number ?? '').toLowerCase().includes(search) ||
            (a.current_renewal?.number ?? '').toLowerCase().includes(search),
        );
      const ordering = sp.get('ordering') ?? 'effective_end_date';
      const desc = ordering.startsWith('-');
      const field = ordering.replace(/^-/, '') as keyof Amm;
      list = [...list].sort((a, b) => {
        const av = a[field] ?? '';
        const bv = b[field] ?? '';
        const cmp = String(av).localeCompare(String(bv));
        return desc ? -cmp : cmp;
      });
      return HttpResponse.json(paginate(list, request));
    }),
  ),
  http.get(
    url('/amms/:id'),
    withAuth((user, { params }) => {
      const amm = db.amms.find((a) => a.id === params.id);
      if (!amm) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      if (!inScope(user, amm.country_iso2)) return forbidden();
      return HttpResponse.json(amm);
    }),
  ),
  http.post(
    url('/amms'),
    withAuth(async (user, { request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const product = db.products.find((p) => p.id === body.product);
      const country = db.countries.find((c) => c.id === body.country || c.iso2 === body.country);
      if (!product || !country)
        return HttpResponse.json({ detail: 'Produit ou pays invalide' }, { status: 400 });
      if (!inScope(user, country.iso2)) return forbidden();
      if (db.amms.some((a) => a.product === product.id && a.country === country.id)) {
        return HttpResponse.json(
          { detail: 'Une AMM existe déjà pour ce produit dans ce pays' },
          { status: 400 },
        );
      }
      const amm: Amm = {
        id: nextId('amm'),
        product: product.id,
        product_name: product.name,
        range_code: product.range_code,
        country: country.id,
        country_iso2: country.iso2,
        country_name: country.name,
        original_number: (body.original_number as string) ?? null,
        original_start_date: (body.original_start_date as string) ?? null,
        original_end_date: (body.original_end_date as string) ?? null,
        original_end_date_manual: !!body.original_end_date_manual,
        status: 'INDETERMINE',
        urgency: 'A_PLANIFIER',
        effective_end_date: null,
        filing_deadline: null,
        dossier_state: (body.dossier_state as Amm['dossier_state']) ?? 'INCONNU',
        notes: (body.notes as string) ?? '',
        owner: null,
        has_current_scan: false,
        current_renewal: null,
        updated_at: new Date().toISOString(),
      };
      db.amms.push(amm);
      recomputeAmm(db, amm.id);
      addHistory(amm.id, user, 'CREATE', [{ field: 'original_number', old: null, new: amm.original_number }]);
      return HttpResponse.json(amm, { status: 201 });
    }),
  ),
  http.patch(
    url('/amms/:id'),
    withAuth(async (user, { request, params }) => {
      const amm = db.amms.find((a) => a.id === params.id);
      if (!amm) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      if (!inScope(user, amm.country_iso2)) return forbidden();
      const body = (await request.json()) as Record<string, unknown>;
      const changes = Object.entries(body)
        .filter(([k, v]) => (amm as unknown as Record<string, unknown>)[k] !== v)
        .map(([k, v]) => ({ field: k, old: (amm as unknown as Record<string, unknown>)[k], new: v }));
      Object.assign(amm, body);
      if ('original_end_date' in body && body.original_end_date) amm.original_end_date_manual = true;
      recomputeAmm(db, amm.id);
      if (changes.length) addHistory(amm.id, user, 'UPDATE', changes);
      return HttpResponse.json(amm);
    }),
  ),
  http.get(
    url('/amms/:id/history'),
    withAuth((_u, { params }) => HttpResponse.json(db.history[String(params.id)] ?? [])),
  ),

  // ---- Renouvellements ----
  http.get(
    url('/amms/:id/renewals'),
    withAuth((_u, { params }) => HttpResponse.json(db.renewals.filter((r) => r.amm === params.id))),
  ),
  http.post(
    url('/amms/:id/renewals'),
    withAuth(async (user, { request, params }) => {
      const amm = db.amms.find((a) => a.id === params.id);
      if (!amm) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      if (!inScope(user, amm.country_iso2)) return forbidden();
      const existing = db.renewals.filter((r) => r.amm === amm.id);
      if (existing.some((r) => !['OBTENU', 'REJETE', 'ABANDONNE'].includes(r.workflow_status))) {
        return HttpResponse.json(
          { detail: 'Un renouvellement est déjà en cours pour cette AMM' },
          { status: 400 },
        );
      }
      const body = (await request.json()) as Partial<Renewal>;
      const renewal: Renewal = {
        id: nextId('ren'),
        amm: amm.id,
        sequence: existing.length + 1,
        workflow_status: 'PLANIFIE',
        filing_date: null,
        decision_date: null,
        number: null,
        start_date: null,
        end_date: null,
        end_date_manual: false,
        notes: body.notes ?? '',
        created_at: new Date().toISOString(),
      };
      db.renewals.push(renewal);
      recomputeAmm(db, amm.id);
      addHistory(amm.id, user, 'RENEWAL_CREATED', [
        { field: 'renewal', old: null, new: `#${renewal.sequence}` },
      ]);
      return HttpResponse.json(renewal, { status: 201 });
    }),
  ),
  http.get(
    url('/renewals/:id'),
    withAuth((_u, { params }) => {
      const renewal = db.renewals.find((r) => r.id === params.id);
      return renewal
        ? HttpResponse.json(renewal)
        : HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
    }),
  ),
  http.post(
    url('/renewals/:id/transition'),
    withAuth(async (user, { request, params }) => {
      const renewal = db.renewals.find((r) => r.id === params.id);
      if (!renewal) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const body = (await request.json()) as {
        to: WorkflowStatus;
        filing_date?: string;
        decision_date?: string;
        number?: string;
        start_date?: string;
        end_date?: string;
        notes?: string;
      };
      if (!TRANSITIONS[renewal.workflow_status].includes(body.to)) {
        return HttpResponse.json(
          { detail: `Transition ${renewal.workflow_status} → ${body.to} interdite` },
          { status: 400 },
        );
      }
      if (body.to === 'DEPOSE' && !body.filing_date)
        return HttpResponse.json({ filing_date: ['La date de dépôt est obligatoire'] }, { status: 400 });
      if (body.to === 'OBTENU' && (!body.number || !body.start_date))
        return HttpResponse.json({ detail: 'Numéro et date de début obligatoires' }, { status: 400 });
      const old = renewal.workflow_status;
      renewal.workflow_status = body.to;
      if (body.filing_date) renewal.filing_date = body.filing_date;
      if (body.decision_date) renewal.decision_date = body.decision_date;
      if (body.number) renewal.number = body.number;
      if (body.start_date) renewal.start_date = body.start_date;
      if (body.end_date) {
        renewal.end_date = body.end_date;
        renewal.end_date_manual = true;
      }
      if (body.notes) renewal.notes = body.notes;
      recomputeAmm(db, renewal.amm);
      addHistory(renewal.amm, user, 'RENEWAL_TRANSITION', [
        { field: `renewal#${renewal.sequence}.workflow_status`, old, new: body.to },
      ]);
      if (['DEPOSE', 'OBTENU'].includes(body.to)) {
        for (const al of db.alerts) {
          if (
            al.amm === renewal.amm &&
            al.status !== 'RESOLVED' &&
            (body.to === 'OBTENU' || ['J-180', 'J-90', 'J-30'].includes(al.rule_code))
          ) {
            al.status = 'RESOLVED';
            al.resolved_at = new Date().toISOString();
            al.resolution = body.to === 'OBTENU' ? 'AUTO_RENEWED' : 'AUTO_FILED';
          }
        }
      }
      return HttpResponse.json(renewal);
    }),
  ),

  // ---- Documents ----
  http.get(
    url('/amms/:id/documents'),
    withAuth((user, { request, params }) => {
      const amm = db.amms.find((a) => a.id === params.id);
      if (!amm) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      if (!inScope(user, amm.country_iso2)) return forbidden();
      const sp = new URL(request.url).searchParams;
      const includeArchived = sp.get('include_archived') === '1';
      const docs = sortDocs(
        db.documents.filter((d) => d.amm === amm.id && (includeArchived || (d.is_current && !d.archived_at))),
      );
      if (sp.get('group') !== 'period') return HttpResponse.json(docs);
      const renewals = db.renewals.filter((r) => r.amm === amm.id).sort((a, b) => b.sequence - a.sequence);
      const groups: DocumentPeriod[] = renewals.map((r) => ({
        period: 'RENEWAL' as const,
        sequence: r.sequence,
        label: `Renouvellement n°${r.sequence}${r.number ? ` — ${r.number}` : ''}`,
        documents: docs.filter((d) => d.renewal === r.id),
      }));
      groups.push({
        period: 'ORIGINAL',
        sequence: null,
        label: `AMM d'origine${amm.original_number ? ` — ${amm.original_number}` : ''}`,
        documents: docs.filter((d) => d.renewal === null),
      });
      return HttpResponse.json(groups);
    }),
  ),
  http.post(
    url('/amms/:id/documents'),
    withAuth(async (user, { request, params }) => {
      await delay(150);
      const amm = db.amms.find((a) => a.id === params.id);
      if (!amm) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      if (!inScope(user, amm.country_iso2)) return forbidden();
      const { form, file } = await readForm(request);
      if (!file) return HttpResponse.json({ file: ['Fichier requis'] }, { status: 400 });
      const doc = createDoc(amm, null, form, file, user);
      return HttpResponse.json(doc, { status: 201 });
    }),
  ),
  http.post(
    url('/renewals/:id/documents'),
    withAuth(async (user, { request, params }) => {
      await delay(150);
      const renewal = db.renewals.find((r) => r.id === params.id);
      if (!renewal) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const amm = db.amms.find((a) => a.id === renewal.amm)!;
      if (!inScope(user, amm.country_iso2)) return forbidden();
      const { form, file } = await readForm(request);
      if (!file) return HttpResponse.json({ file: ['Fichier requis'] }, { status: 400 });
      const doc = createDoc(amm, renewal, form, file, user);
      return HttpResponse.json(doc, { status: 201 });
    }),
  ),
  http.post(
    url('/documents/:id/replace'),
    withAuth(async (user, { request, params }) => {
      await delay(150);
      const old = db.documents.find((d) => d.id === params.id);
      if (!old) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const { form, file } = await readForm(request);
      if (!file) return HttpResponse.json({ file: ['Fichier requis'] }, { status: 400 });
      old.is_current = false;
      const amm = db.amms.find((a) => a.id === old.amm)!;
      const renewal = old.renewal ? (db.renewals.find((r) => r.id === old.renewal) ?? null) : null;
      const doc = createDoc(amm, renewal, form, file, user, {
        version: old.version + 1,
        replaces: old.id,
        kind: old.kind,
        document_date: old.document_date,
        title: old.title,
      });
      return HttpResponse.json(doc, { status: 201 });
    }),
  ),
  http.delete(
    url('/documents/:id'),
    withAuth((user, { params }) => {
      if (user.role !== 'CEO_ADMIN') return forbidden();
      const doc = db.documents.find((d) => d.id === params.id);
      if (!doc) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      doc.archived_at = new Date().toISOString();
      doc.is_current = false;
      recomputeAmm(db, doc.amm);
      addHistory(doc.amm, user, 'DOCUMENT_ARCHIVED', [{ field: 'document', old: doc.title, new: null }]);
      return new HttpResponse(null, { status: 204 });
    }),
  ),
  http.get(
    url('/documents/:id/file'),
    withAuth((_u, { request }) => {
      const download = new URL(request.url).searchParams.get('download') === '1';
      return new HttpResponse(SAMPLE_PDF, {
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': `${download ? 'attachment' : 'inline'}; filename="document.pdf"`,
        },
      });
    }),
  ),
  http.get(
    url('/amms/:id/documents/archive.zip'),
    withAuth(
      () => new HttpResponse(new Blob(['PK mock zip']), { headers: { 'Content-Type': 'application/zip' } }),
    ),
  ),

  // ---- Alertes ----
  http.get(
    url('/alerts'),
    withAuth((user, { request }) => {
      const sp = new URL(request.url).searchParams;
      let list = db.alerts.filter((a) => inScope(user, a.amm_summary.country_iso2));
      const status = sp.get('status');
      if (status) list = list.filter((a) => a.status === status);
      const country = sp.get('country');
      if (country) list = list.filter((a) => a.amm_summary.country_iso2 === country);
      const severity = sp.get('severity');
      if (severity) list = list.filter((a) => a.severity === severity);
      if (sp.get('assigned_to') === 'me') list = list.filter((a) => a.assigned_to === user.id);
      const amm = sp.get('amm');
      if (amm) list = list.filter((a) => a.amm === amm);
      list = [...list].sort((a, b) => a.due_date.localeCompare(b.due_date));
      return HttpResponse.json(paginate(list, request));
    }),
  ),
  http.post(
    url('/alerts/:id/acknowledge'),
    withAuth((_u, { params }) => {
      const al = db.alerts.find((a) => a.id === params.id);
      if (!al) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      al.status = 'ACKNOWLEDGED';
      al.acknowledged_at = new Date().toISOString();
      return HttpResponse.json(al);
    }),
  ),
  http.post(
    url('/alerts/:id/assign'),
    withAuth(async (_u, { request, params }) => {
      const al = db.alerts.find((a) => a.id === params.id);
      if (!al) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const body = (await request.json()) as { user_id: string };
      const target = db.users.find((u) => u.id === body.user_id);
      al.assigned_to = target?.id ?? null;
      al.assigned_to_email = target?.email ?? null;
      return HttpResponse.json(al);
    }),
  ),
  http.post(
    url('/alerts/:id/resolve'),
    withAuth(async (_u, { request, params }) => {
      const al = db.alerts.find((a) => a.id === params.id);
      if (!al) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const body = (await request.json()) as { comment: string };
      al.status = 'RESOLVED';
      al.resolved_at = new Date().toISOString();
      al.resolution = 'MANUAL';
      al.comment = body.comment;
      return HttpResponse.json(al);
    }),
  ),
  http.get(
    url('/alert-rules'),
    withAuth((_u, { request }) => HttpResponse.json(paginate(db.alertRules, request))),
  ),
  http.post(
    url('/alert-rules'),
    withAuth(async (_u, { request }) => {
      const body = (await request.json()) as Partial<AlertRule>;
      const rule: AlertRule = {
        id: nextId('rule'),
        code: 'J-180',
        country: null,
        offset_days: 180,
        severity: 'WARNING',
        roles: [],
        channels: ['in_app'],
        only_if_not_filed: true,
        is_active: true,
        ...body,
      };
      db.alertRules.push(rule);
      return HttpResponse.json(rule, { status: 201 });
    }),
  ),
  http.patch(
    url('/alert-rules/:id'),
    withAuth(async (_u, { request, params }) => {
      const rule = db.alertRules.find((r) => r.id === params.id);
      if (!rule) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      Object.assign(rule, await request.json());
      return HttpResponse.json(rule);
    }),
  ),
  http.delete(
    url('/alert-rules/:id'),
    withAuth((_u, { params }) => {
      db.alertRules = db.alertRules.filter((r) => r.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  ),

  // ---- Notifications ----
  http.get(
    url('/notifications/unread-count'),
    withAuth(() => HttpResponse.json({ count: db.notifications.filter((n) => !n.read_at).length })),
  ),
  http.get(
    url('/notifications'),
    withAuth((_u, { request }) => {
      const unread = new URL(request.url).searchParams.get('unread') === '1';
      const list = db.notifications
        .filter((n) => !unread || !n.read_at)
        .sort((a, b) => b.sent_at.localeCompare(a.sent_at));
      return HttpResponse.json(paginate(list, request));
    }),
  ),
  http.post(
    url('/notifications/read-all'),
    withAuth(() => {
      for (const n of db.notifications) n.read_at = n.read_at ?? new Date().toISOString();
      return new HttpResponse(null, { status: 204 });
    }),
  ),
  http.post(
    url('/notifications/:id/read'),
    withAuth((_u, { params }) => {
      const n = db.notifications.find((x) => x.id === params.id);
      if (n) n.read_at = new Date().toISOString();
      return new HttpResponse(null, { status: 204 });
    }),
  ),

  // ---- Analytics ----
  http.get(
    url('/analytics/africa'),
    withAuth((user) => HttpResponse.json(africaRows(user))),
  ),
  http.get(
    url('/analytics/country/:iso2'),
    withAuth((user, { params }) => {
      const iso2 = String(params.iso2);
      if (!inScope(user, iso2)) return forbidden();
      const amms = db.amms.filter((a) => a.country_iso2 === iso2);
      const byKey = new Map<string, { range: string; status: Amm['status']; count: number }>();
      for (const a of amms) {
        const key = `${a.range_code}|${a.status}`;
        const entry = byKey.get(key) ?? { range: a.range_code, status: a.status, count: 0 };
        entry.count += 1;
        byKey.set(key, entry);
      }
      const today = parseISO(MOCK_TODAY);
      const pipeline = Array.from({ length: 24 }, (_, i) => {
        const month = format(addMonths(today, i), 'yyyy-MM');
        const count = amms.filter(
          (a) => a.effective_end_date && a.effective_end_date.startsWith(month),
        ).length;
        return { month, count };
      });
      const order = ['EXPIRE', 'CRITIQUE', 'DEPOT_URGENT', 'EN_INSTRUCTION', 'A_PLANIFIER', 'OK'];
      const priorities = [...amms]
        .sort(
          (a, b) =>
            order.indexOf(a.urgency) - order.indexOf(b.urgency) ||
            (a.effective_end_date ?? '').localeCompare(b.effective_end_date ?? ''),
        )
        .slice(0, 10);
      void differenceInCalendarMonths;
      return HttpResponse.json({ by_range_status: Array.from(byKey.values()), pipeline, priorities });
    }),
  ),
  http.get(
    url('/analytics/product/:id/coverage'),
    withAuth((_u, { params }) =>
      HttpResponse.json(
        db.countries.map((c) => {
          const amm = db.amms.find((a) => a.product === params.id && a.country_iso2 === c.iso2);
          return {
            country_iso2: c.iso2,
            country_name: c.name,
            status: amm?.status ?? null,
            effective_end_date: amm?.effective_end_date ?? null,
          };
        }),
      ),
    ),
  ),
  http.get(
    url('/analytics/export'),
    withAuth(
      () =>
        new HttpResponse(new Blob(['mock xlsx']), {
          headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
        }),
    ),
  ),

  // ---- Users ----
  http.get(
    url('/users'),
    withAuth((user, { request }) => {
      if (user.role === 'COUNTRY_REGULATORY') return forbidden();
      return HttpResponse.json(paginate(db.users, request));
    }),
  ),
  http.post(
    url('/users'),
    withAuth(async (user, { request }) => {
      const body = (await request.json()) as Partial<User> & { password?: string };
      if (user.role === 'COUNTRY_REGULATORY') return forbidden();
      if (user.role === 'HQ_REGULATORY' && body.role !== 'COUNTRY_REGULATORY') return forbidden();
      const created: User = {
        id: nextId('u'),
        email: '',
        first_name: '',
        last_name: '',
        role: 'COUNTRY_REGULATORY',
        countries: [],
        is_active: true,
        ...body,
      };
      delete (created as { password?: string }).password;
      db.users.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
  ),
  http.patch(
    url('/users/:id'),
    withAuth(async (user, { request, params }) => {
      if (user.role === 'COUNTRY_REGULATORY') return forbidden();
      const target = db.users.find((u) => u.id === params.id);
      if (!target) return HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
      const body = (await request.json()) as Partial<User> & { password?: string };
      delete body.password;
      Object.assign(target, body);
      return HttpResponse.json(target);
    }),
  ),
  http.delete(
    url('/users/:id'),
    withAuth((user, { params }) => {
      if (user.role !== 'CEO_ADMIN') return forbidden();
      db.users = db.users.filter((u) => u.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  ),

  // ---- Imports ----
  http.get(
    url('/imports'),
    withAuth((_u, { request }) => HttpResponse.json(paginate([...db.imports].reverse(), request))),
  ),
  http.post(
    url('/imports'),
    withAuth(async (user, { request }) => {
      if (user.role === 'COUNTRY_REGULATORY') return forbidden();
      const { file } = await readForm(request);
      const batch = {
        id: nextId('imp'),
        status: 'RUNNING',
        summary: null,
        created_at: new Date().toISOString(),
        file_name: file?.name ?? 'classeur.xlsx',
      };
      db.imports.push(batch);
      db.importRows[batch.id] = [];
      setTimeout(() => {
        batch.status = 'DONE';
        batch.summary = { created: 0, updated: 10, skipped: 2, errors: 1, warnings: 0 } as never;
        db.importRows[batch.id] = [
          {
            sheet: 'CAMEROUN',
            row_number: 14,
            raw: { NOM: 'PARACETAMOL 1 G CP B/8', 'DATE DEBUT': 'DATE ILLISIBLE' },
            outcome: 'ERROR',
            message: 'Date de début illisible',
          },
        ];
      }, 1500);
      return HttpResponse.json(batch, { status: 202 });
    }),
  ),
  http.get(
    url('/imports/:id'),
    withAuth((_u, { params }) => {
      const batch = db.imports.find((b) => b.id === params.id);
      return batch ? HttpResponse.json(batch) : HttpResponse.json({ detail: 'Introuvable' }, { status: 404 });
    }),
  ),
  http.get(
    url('/imports/:id/rows'),
    withAuth((_u, { request, params }) => {
      const outcome = new URL(request.url).searchParams.get('outcome');
      const rows = (db.importRows[String(params.id)] ?? []).filter((r) => !outcome || r.outcome === outcome);
      return HttpResponse.json(paginate(rows, request));
    }),
  ),
];

function createDoc(
  amm: Amm,
  renewal: Renewal | null,
  form: FormData,
  file: File,
  user: User,
  overrides: Partial<AmmDocument> = {},
): AmmDocument {
  const id = nextId('doc');
  const doc: AmmDocument = {
    id,
    amm: amm.id,
    renewal: renewal?.id ?? null,
    kind: (form.get('kind') as AmmDocument['kind']) || 'AMM',
    title: String(form.get('title') || file.name.replace(/\.[^.]+$/, '')),
    document_date: String(
      form.get('document_date') || renewal?.start_date || amm.original_start_date || MOCK_TODAY,
    ),
    sha256: `sha-${id}`,
    size_bytes: file.size,
    page_count: 1,
    version: 1,
    replaces: null,
    is_current: true,
    uploaded_by_email: user.email,
    uploaded_at: new Date().toISOString(),
    archived_at: null,
    file_url: `/api/v1/documents/${id}/file`,
    ...overrides,
  };
  db.documents.push(doc);
  recomputeAmm(db, amm.id);
  addHistory(amm.id, user, overrides.replaces ? 'DOCUMENT_REPLACED' : 'DOCUMENT_ADDED', [
    { field: 'document', old: overrides.replaces ?? null, new: doc.title },
  ]);
  return doc;
}
