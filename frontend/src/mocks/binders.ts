import { http, HttpResponse, passthrough } from 'msw';
import type { BinderDetail, BinderPage } from '@/api/types';
import { db } from './handlers';

/**
 * Classeurs en mode démonstration (navigateur seulement) : un classeur par pays, une page par AMM.
 * Les tests montent leurs propres réponses ; ces maquettes servent à `npm run dev:mock`.
 */
const counts = { total: 0, checked: 0, conformes: 0, corrected: 0, absent: 0, to_scan: 0 };

function pageOf(index: number, amm: (typeof db.amms)[number]): BinderPage {
  const renewals = db.renewals
    .filter((r) => r.amm_id === amm.id && r.workflow_status === 'OBTENU')
    .sort((a, b) => b.sequence - a.sequence);
  const last = renewals[0];
  return {
    amm_id: amm.id,
    page: index + 1,
    section_page: index + 1,
    product_name: amm.product_name,
    range_code: amm.range_code ?? 'GENERALE',
    range_label: amm.range_code ?? 'Générale',
    original: {
      number: amm.original_number,
      start_date: amm.original_start_date,
      end_date: amm.original_end_date,
    },
    renewal: last
      ? {
          id: last.id,
          sequence: last.sequence,
          number: last.number,
          start_date: last.start_date,
          end_date: last.end_date,
        }
      : null,
    pending_renewal: null,
    status: amm.status,
    status_label: amm.status,
    dossier_state: amm.dossier_state,
    scan: null,
    decision_count: 0,
    chronology: [],
    discrepancies: [],
    check: null,
    to_scan: false,
    changed_since_check: [],
    changed_by: null,
    trace: { excel: null, dossier: null },
  } as BinderPage;
}

function binderOf(iso2: string): BinderDetail {
  const amms = db.amms.filter((a) => a.country_iso2 === iso2);
  const pages = amms.map((amm, index) => pageOf(index, amm));
  const total = { ...counts, total: pages.length };
  return {
    key: iso2,
    title: 'Toutes gammes',
    country_iso2: iso2,
    country_name: amms[0]?.country_name ?? iso2,
    is_headquarters: false,
    ...total,
    extras: 0,
    last_checked_at: null,
    last_checked_by: null,
    readers: [],
    sections: [{ code: 'GENERALE', label: 'Générale', color: '#1565c0', ...total, pages, stale: 0 }],
    extra_pages: [],
    resume_page: 1,
    stale: 0,
  } as BinderDetail;
}

export const binderHandlers = [
  http.get('/api/v1/binders/locate', ({ request }) => {
    const amm = db.amms.find((a) => a.id === new URL(request.url).searchParams.get('amm'));
    if (!amm) return passthrough();
    const pages = db.amms.filter((a) => a.country_iso2 === amm.country_iso2);
    return HttpResponse.json({
      binder_key: amm.country_iso2,
      title: 'Toutes gammes',
      country_name: amm.country_name,
      page: pages.indexOf(amm) + 1,
      total: pages.length,
      check: null,
      stale: false,
    });
  }),
  http.get('/api/v1/binders/:key', ({ params }) => HttpResponse.json(binderOf(String(params.key)))),
  http.post('/api/v1/binders/:key/presence', () => HttpResponse.json({})),
  http.post('/api/v1/binders/:key/check', ({ params }) => HttpResponse.json(binderOf(String(params.key)))),
];
