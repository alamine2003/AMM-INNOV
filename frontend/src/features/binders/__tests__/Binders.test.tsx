import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { BinderDetail, BinderPage, BinderSummary } from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';
import { buildLeaves, resumeIndex } from '../leaves';

const endpoint = '/api/v1/binders';

const counts = { total: 2, checked: 1, conformes: 1, corrected: 0, absent: 0, to_scan: 0 };

function page(overrides: Partial<BinderPage> = {}): BinderPage {
  return {
    amm_id: 'amm-1',
    page: 1,
    section_page: 1,
    product_name: 'AMLODIPINE GH 5MG',
    range_code: 'CARDIO',
    range_label: 'Cardio',
    original: { number: 'AMM/SN/2010/0152', start_date: '2010-12-22', end_date: '2015-12-22' },
    renewal: null,
    status: 'VALIDE',
    status_label: 'Valide',
    dossier_state: 'COMPLET',
    scan: null,
    discrepancies: [],
    check: null,
    to_scan: false,
    ...overrides,
  };
}

const checked = page({
  amm_id: 'amm-0',
  product_name: 'ACARBOSE GH 100MG',
  check: {
    result: 'CONFORME',
    corrections: [],
    note: '',
    checked_by: 'Fatou',
    checked_at: '2026-09-27T10:00:00Z',
  },
});

function binder(pages: BinderPage[]): BinderDetail {
  return {
    key: 'SN-cardio',
    title: 'Cardio',
    country_iso2: 'SN',
    country_name: 'Sénégal',
    is_headquarters: true,
    ...counts,
    extras: 0,
    last_checked_at: null,
    last_checked_by: null,
    sections: [{ code: 'CARDIO', label: 'Cardio', color: '#c62828', ...counts, pages }],
    extra_pages: [],
    resume_page: 2,
  };
}

const summary: BinderSummary = {
  key: 'SN-cardio',
  title: 'Cardio',
  country_iso2: 'SN',
  country_name: 'Sénégal',
  is_headquarters: true,
  ...counts,
  extras: 0,
  last_checked_at: null,
  last_checked_by: null,
  sections: [{ code: 'CARDIO', label: 'Cardio', color: '#c62828', ...counts }],
};

describe('ordre des feuilles', () => {
  it('reprend à la première page non vérifiée et filtre sans perdre les intercalaires', () => {
    const data = binder([
      checked,
      page({ page: 2, discrepancies: [] }),
      page({ amm_id: 'amm-2', scan: null }),
    ]);
    const all = buildLeaves(data, 'all');
    expect(all.map((leaf) => leaf.key)).toEqual([
      'title',
      'divider:CARDIO',
      'page:amm-0',
      'page:amm-1',
      'page:amm-2',
      'end',
    ]);
    expect(resumeIndex(all, data)).toBe(3);
    const unchecked = buildLeaves(data, 'unchecked').map((leaf) => leaf.key);
    expect(unchecked).toEqual(['title', 'divider:CARDIO', 'page:amm-1', 'page:amm-2', 'end']);
  });
});

describe('Classeurs', () => {
  it("le siège voit l'étagère et peut télécharger", async () => {
    loginAs('u-hq');
    server.use(http.get(endpoint, () => HttpResponse.json([summary])));
    renderApp('/classeurs');
    expect(await screen.findByTestId('spine-SN-cardio')).toBeInTheDocument();
    expect(screen.getByLabelText(/Télécharger le classeur Sénégal Cardio/)).toBeInTheDocument();
  });

  it('le siège prépare et télécharge le classeur avec les décisions officielles', async () => {
    loginAs('u-hq');
    let started = false;
    server.use(
      http.get(endpoint, () => HttpResponse.json([summary])),
      http.get(`${endpoint}/SN-cardio/exports`, () =>
        HttpResponse.json(
          started
            ? [
                {
                  id: 'exp-1',
                  binder_key: 'SN-cardio',
                  status: 'READY',
                  progress_done: 94,
                  progress_total: 94,
                  size_bytes: 52_428_800,
                  page_count: 402,
                  decisions: 88,
                  unavailable: 0,
                  without_scan: 6,
                  error: '',
                  created_by: 'Siège',
                  created_at: '2026-09-27T10:00:00Z',
                  started_at: '2026-09-27T10:00:01Z',
                  finished_at: '2026-09-27T10:03:00Z',
                  has_file: true,
                },
              ]
            : [],
        ),
      ),
      http.post(`${endpoint}/SN-cardio/exports`, () => {
        started = true;
        return HttpResponse.json({}, { status: 202 });
      }),
    );
    renderApp('/classeurs');
    await userEvent.click(await screen.findByLabelText(/Télécharger le classeur Sénégal Cardio/));
    await userEvent.click(await screen.findByText('Avec les décisions officielles'));
    await userEvent.click(await screen.findByRole('button', { name: 'Préparer le classeur' }));
    expect(await screen.findByText(/88 décisions officielles jointes/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Télécharger' })).toBeInTheDocument();
  });

  it('un pays ne voit pas le téléchargement', async () => {
    loginAs('u-sn');
    server.use(http.get(endpoint, () => HttpResponse.json([summary])));
    renderApp('/classeurs');
    await screen.findByTestId('spine-SN-cardio');
    expect(screen.queryByLabelText(/Télécharger le classeur/)).not.toBeInTheDocument();
  });

  it("s'ouvre sur la page à vérifier et tamponne « Conforme »", async () => {
    loginAs('u-sn');
    const open = page();
    let sent: unknown = null;
    server.use(
      http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, open]))),
      http.post(`${endpoint}/SN-cardio/check`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(
          binder([checked, { ...open, check: { ...checked.check!, checked_at: '2026-09-27T11:00:00Z' } }]),
        );
      }),
    );
    renderApp('/classeurs/SN-cardio');
    const book = await screen.findByTestId('binder-book');
    const current = within(book).getAllByTestId('binder-sheet')[0];
    expect(within(current).getByText('AMLODIPINE GH 5MG')).toBeInTheDocument();
    await userEvent.click(within(current).getByRole('button', { name: /Conforme/ }));
    await waitFor(() => expect(sent).toMatchObject({ amm: 'amm-1', result: 'CONFORME' }));
    expect(await within(book).findAllByTestId('binder-stamp')).not.toHaveLength(0);
  });
});
