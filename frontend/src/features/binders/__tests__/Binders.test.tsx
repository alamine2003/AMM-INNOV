import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type {
  BinderConformity,
  BinderCriterionKey,
  BinderDetail,
  BinderPage,
  BinderSummary,
} from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';
import { buildLeaves, resumeIndex, type LeafFilter } from '../leaves';

/** Pages gardées par un filtre du classeur. */
const data = (detail: BinderDetail, filter: LeafFilter) =>
  buildLeaves(detail, filter)
    .filter((leaf) => leaf.kind === 'page')
    .map((leaf) => (leaf.kind === 'page' ? leaf.ammId : ''));

const endpoint = '/api/v1/binders';

const counts = {
  total: 2,
  checked: 1,
  conformes: 1,
  non_conformes: 0,
  corrected: 0,
  absent: 0,
  to_scan: 0,
  stale: 0,
};

function conformity(
  status: BinderConformity['status'],
  ok: Record<BinderCriterionKey, boolean | null>,
): BinderConformity {
  const labels = {
    CONFORME: 'Le dossier est conforme',
    NON_CONFORME: 'Dossier non conforme',
    NON_VERIFIE: 'Dossier pas encore vérifié',
  };
  return {
    status,
    label: labels[status],
    criteria: [
      {
        key: 'digital',
        label: 'Visible dans le classeur numérique',
        ok: ok.digital,
        detail: 'fiche dans AMM GH',
      },
      { key: 'paper', label: 'Dossier papier dans le classeur', ok: ok.paper, detail: 'présent' },
      {
        key: 'scan',
        label: 'Version scannée',
        ok: ok.scan,
        detail: ok.scan ? 'décision scannée' : 'aucun scan de décision',
      },
      {
        key: 'data',
        label: "Bonne date et bon n° d'AMM",
        ok: ok.data,
        detail: 'n° AMM/SN/2010/0152 du 22/12/2010',
      },
    ],
    to_scan: ok.paper === true && ok.scan === false,
    stale: false,
  };
}

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
    pending_renewal: null,
    status: 'VALIDE',
    status_label: 'Valide',
    dossier_state: 'COMPLET',
    scan: null,
    decision_count: 0,
    chronology: [],
    discrepancies: [],
    check: null,
    to_scan: false,
    conformity: conformity('NON_VERIFIE', { digital: true, paper: null, scan: false, data: null }),
    changed_since_check: [],
    changed_by: null,
    trace: { excel: null, dossier: null },
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
  conformity: conformity('CONFORME', { digital: true, paper: true, scan: true, data: true }),
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
    readers: [],
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
  readers: [],
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

  it("s'ouvre sur la page à vérifier et tamponne « Papier conforme »", async () => {
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
    const book = await screen.findByTestId('binder-book', {}, { timeout: 5000 });
    const current = within(book).getAllByTestId('binder-sheet')[0];
    expect(within(current).getByText('AMLODIPINE GH 5MG')).toBeInTheDocument();
    // Les 4 niveaux : numérique juste, papier et date/n° à constater, pas de scan.
    const panel = within(current).getByTestId('page-conformity');
    expect(panel).toHaveTextContent('1. Visible dans le classeur numérique');
    expect(panel).toHaveTextContent('3. Version scannée — aucun scan de décision');
    expect(within(current).getByTestId('page-verdict')).toHaveTextContent(
      'Résultat : Dossier pas encore vérifié',
    );
    await userEvent.click(within(current).getByRole('button', { name: /Papier conforme/ }));
    await waitFor(() => expect(sent).toMatchObject({ amm: 'amm-1', result: 'CONFORME' }));
    expect(await within(book).findAllByTestId('binder-stamp')).not.toHaveLength(0);
  });

  it('montre « Le dossier est conforme » quand les 4 niveaux sont justes', async () => {
    loginAs('u-sn');
    const missing = page({
      check: { ...checked.check! },
      conformity: conformity('NON_CONFORME', { digital: true, paper: true, scan: false, data: true }),
    });
    server.use(http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, missing]))));
    renderApp('/classeurs/SN-cardio?amm=amm-0');
    const book = await screen.findByTestId('binder-book', {}, { timeout: 5000 });
    const current = (await within(book).findAllByTestId('binder-sheet'))[0];
    expect(within(current).getByTestId('page-verdict')).toHaveTextContent(
      'Résultat : Le dossier est conforme',
    );
    // Le filtre « Dossiers non conformes » ne garde que la page sans scan.
    expect(data(binder([checked, missing]), 'non_conformes')).toEqual(['amm-1']);
  });

  it('corrige une date de début : la fin se recalcule sur 5 ans', async () => {
    loginAs('u-sn');
    const open = page();
    let sent: { corrections?: { slot: string; field: string; value: string | null }[] } | null = null;
    server.use(
      http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, open]))),
      http.post(`${endpoint}/SN-cardio/check`, async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return HttpResponse.json(binder([checked, open]));
      }),
    );
    renderApp('/classeurs/SN-cardio');
    const book = await screen.findByTestId('binder-book');
    const current = within(book).getAllByTestId('binder-sheet')[0];
    await userEvent.click(within(current).getByRole('button', { name: /Corriger/ }));
    fireEvent.change(within(current).getByTestId('sheet-original.start_date'), {
      target: { value: '16/04/2016' },
    });
    expect(within(current).getByTestId('sheet-original.end_date')).toHaveValue('16/04/2021');
    expect(within(current).getAllByTestId('validity-line')[0]).toHaveTextContent(
      "Validité : 5 ans, jusqu'au 16/04/2021",
    );
    await userEvent.click(within(current).getByRole('button', { name: 'Valider la correction' }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent!.corrections).toEqual([
      { slot: 'original', field: 'start_date', value: '2016-04-16' },
      { slot: 'original', field: 'end_date', value: '2021-04-16' },
    ]);
  });

  it('empile les décisions et ouvre la chronologie avec ce qui manque', async () => {
    loginAs('u-sn');
    const doc = (id: string, date: string) => ({
      document_id: id,
      kind: 'AMM',
      kind_label: 'AMM',
      document_date: date,
      title: `Décision ${date}`,
      page_count: 2,
    });
    const stacked = page({
      decision_count: 2,
      scan: { document_id: 'doc-r2', document_date: '2024-01-10', page_count: 2 },
      chronology: [
        {
          kind: 'renewal',
          label: 'Renouvellement 2',
          renewal_id: 'r2',
          number: 'R2',
          start_date: '2024-01-10',
          end_date: '2029-01-10',
          decisions: [doc('doc-r2', '2024-01-10')],
          others: [],
          issues: [],
        },
        {
          kind: 'gap',
          label: 'Interruption de validité',
          start_date: '2022-03-01',
          end_date: '2024-01-10',
          issues: [{ code: 'gap', message: 'Aucune décision ne couvre cette période.' }],
        },
        {
          kind: 'renewal',
          label: 'Renouvellement 1',
          renewal_id: 'r1',
          number: 'R1',
          start_date: '2017-03-01',
          end_date: '2022-03-01',
          decisions: [],
          others: [],
          issues: [{ code: 'no_scan', message: 'Décision non scannée.' }],
        },
        {
          kind: 'origin',
          label: "AMM d'origine",
          number: 'AMM/SN/2010/0152',
          start_date: '2012-03-01',
          end_date: '2017-03-01',
          decisions: [doc('doc-o', '2012-03-01')],
          others: [],
          issues: [],
        },
      ],
    });
    server.use(http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, stacked]))));
    renderApp('/classeurs/SN-cardio');
    const book = await screen.findByTestId('binder-book', {}, { timeout: 5000 });
    const current = within(book).getAllByTestId('binder-sheet')[0];
    expect(within(current).getAllByTestId('scan-stack-sheet')).toHaveLength(1);
    // Petit bouton d'impression sur la miniature du scan.
    expect(within(current).getByRole('button', { name: /Imprimer le scan du/ })).toBeInTheDocument();
    expect(within(current).getByTestId('open-chronology')).toHaveTextContent('2 manques');
    await userEvent.click(within(current).getByRole('button', { name: /Chronologie des 2 décisions/ }));
    const dialog = await screen.findByTestId('chronology-dialog');
    expect(
      within(dialog)
        .getAllByTestId(/^chronology-/)
        .map((el) => el.dataset.testid),
    ).toEqual(['chronology-renewal', 'chronology-gap', 'chronology-renewal', 'chronology-origin']);
    expect(within(dialog).getByTestId('issue-gap')).toBeInTheDocument();
    expect(within(dialog).getByTestId('issue-no_scan')).toBeInTheDocument();
    expect(within(dialog).getByText(/Décision du 10\/01\/2024/)).toBeInTheDocument();
  });

  describe('la page elle-même', () => {
    async function openPage() {
      renderApp('/classeurs/SN-cardio?amm=amm-1');
      const book = await screen.findByTestId('binder-book', {}, { timeout: 5000 });
      return within(book).getAllByTestId('binder-sheet')[0];
    }

    it('le siège renomme la page : le titre change partout', async () => {
      loginAs('u-ceo');
      let sent: unknown = null;
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, page()]))),
        http.patch(`${endpoint}/SN-cardio/pages/amm-1`, async ({ request }) => {
          sent = await request.json();
          return HttpResponse.json(binder([checked, page({ product_name: 'AMLODIPINE GH 5MG CPR B/30' })]));
        }),
      );
      const sheet = await openPage();
      await userEvent.click(within(sheet).getByTestId('rename-page'));
      const input = await screen.findByTestId('rename-page-input');
      await userEvent.clear(input);
      await userEvent.type(input, 'AMLODIPINE GH 5MG CPR B/30');
      await userEvent.click(screen.getByRole('button', { name: 'Renommer' }));
      await waitFor(() => expect(sent).toEqual({ product_name: 'AMLODIPINE GH 5MG CPR B/30' }));
    });

    it('supprimer une page avec des pièces demande la fiche qui les reprend', async () => {
      loginAs('u-ceo');
      let url = '';
      const withScan = page({
        chronology: [
          {
            kind: 'origin',
            label: "AMM d'origine",
            start_date: '2010-12-22',
            end_date: '2015-12-22',
            decisions: [
              {
                document_id: 'd1',
                kind: 'AMM',
                kind_label: 'Décision',
                document_date: '2010-12-22',
                title: '',
                page_count: 1,
              },
            ],
            others: [],
            issues: [],
          },
        ],
      });
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, withScan]))),
        http.delete(`${endpoint}/SN-cardio/pages/amm-1`, ({ request }) => {
          url = request.url;
          return HttpResponse.json(binder([checked]));
        }),
      );
      const sheet = await openPage();
      await userEvent.click(within(sheet).getByTestId('delete-page'));
      const dialog = await screen.findByTestId('delete-page-dialog');
      expect(dialog).toHaveTextContent('1 pièce');
      expect(within(dialog).getByTestId('delete-page-confirm')).toBeDisabled();
      await userEvent.click(within(dialog).getByLabelText('Fiche qui reprend les pièces'));
      await userEvent.click(await screen.findByRole('option', { name: /ACARBOSE GH 100MG/ }));
      await userEvent.click(within(dialog).getByTestId('delete-page-confirm'));
      await waitFor(() => expect(new URL(url).searchParams.get('move_to_amm')).toBe('amm-0'));
    });

    it('un réglementaire pays ne renomme ni ne supprime de page', async () => {
      loginAs('u-sn');
      server.use(http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, page()]))));
      const sheet = await openPage();
      expect(within(sheet).queryByTestId('rename-page')).toBeNull();
      expect(within(sheet).queryByTestId('delete-page')).toBeNull();
    });

    it('sans renouvellement, pas de bloc à remplir ; il s’ouvre seulement si le papier en porte un', async () => {
      loginAs('u-sn');
      server.use(http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, page()]))));
      const sheet = await openPage();
      expect(within(sheet).queryByText('DERNIER RENOUVELLEMENT')).toBeNull();
      await userEvent.click(within(sheet).getByRole('button', { name: /Corriger/ }));
      expect(within(sheet).queryByText('DERNIER RENOUVELLEMENT')).toBeNull();
      await userEvent.click(within(sheet).getByTestId('add-renewal-slot'));
      expect(within(sheet).getByText('DERNIER RENOUVELLEMENT')).toBeInTheDocument();
    });

    it('ignore une interruption de validité au lieu d’ajouter un passage', async () => {
      loginAs('u-sn');
      let sent: unknown = null;
      const gapped = page({
        chronology: [
          {
            kind: 'gap',
            label: 'Interruption de validité',
            start_date: '2015-12-22',
            end_date: '2020-01-01',
            issues: [{ code: 'gap', message: 'Aucune décision ne couvre cette période.' }],
          },
        ],
      });
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, gapped]))),
        http.post(`${endpoint}/SN-cardio/pages/amm-1/gaps`, async ({ request }) => {
          sent = await request.json();
          return HttpResponse.json(binder([checked, gapped]));
        }),
      );
      const sheet = await openPage();
      await userEvent.click(within(sheet).getByTestId('open-chronology'));
      const dialog = await screen.findByTestId('chronology-dialog');
      await userEvent.click(within(dialog).getByTestId('gap-ignore'));
      await waitFor(() =>
        expect(sent).toEqual({ start_date: '2015-12-22', end_date: '2020-01-01', ignored: true }),
      );
    });
  });

  describe('chronologie modifiable', () => {
    const decision = (id: string, date: string) => ({
      document_id: id,
      kind: 'AMM',
      kind_label: 'AMM',
      document_date: date,
      title: '',
      page_count: 1,
    });
    // Le cas d'ALFA GH : un import a créé le renouvellement 2 en double du 1, avec la décision.
    const doubled = (r1Start = '2025-06-23') =>
      page({
        decision_count: 2,
        scan: { document_id: 'doc-r2', document_date: '2026-08-20', page_count: 1 },
        chronology: [
          {
            kind: 'renewal',
            label: 'Renouvellement 2',
            renewal_id: 'r2',
            sequence: 2,
            number: '9315',
            start_date: '2025-06-23',
            end_date: '2030-06-23',
            decisions: [decision('doc-r2', '2026-08-20')],
            others: [],
            issues: [],
          },
          {
            kind: 'renewal',
            label: 'Renouvellement 1',
            renewal_id: 'r1',
            sequence: 1,
            number: '9315',
            start_date: r1Start,
            end_date: '2030-06-23',
            decisions: [],
            others: [],
            issues: [{ code: 'no_scan', message: 'Décision non scannée.' }],
          },
          {
            kind: 'origin',
            label: "AMM d'origine",
            number: '9315',
            start_date: '2020-06-23',
            end_date: '2025-06-23',
            decisions: [decision('doc-o', '2020-06-23')],
            others: [],
            issues: [],
          },
        ],
      });

    async function openChronology() {
      renderApp('/classeurs/SN-cardio');
      const book = await screen.findByTestId('binder-book');
      const current = within(book).getAllByTestId('binder-sheet')[0];
      await userEvent.click(within(current).getByTestId('open-chronology'));
      return screen.findByTestId('chronology-dialog');
    }

    it("corrige les dates d'une période et la page suit", async () => {
      loginAs('u-sn');
      let sent: unknown = null;
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, doubled()]))),
        http.patch(`${endpoint}/SN-cardio/pages/amm-1/periods/r1`, async ({ request }) => {
          sent = await request.json();
          return HttpResponse.json(binder([checked, doubled('2025-06-24')]));
        }),
      );
      const dialog = await openChronology();
      await userEvent.click(within(dialog).getByRole('button', { name: 'Corriger Renouvellement 1' }));
      const start = within(dialog).getByRole('textbox', { name: 'Date de début' });
      fireEvent.change(start, { target: { value: '24/06/2025' } });
      // La fin suit : début + 5 ans.
      expect(within(dialog).getByRole('textbox', { name: 'Date de fin' })).toHaveValue('24/06/2030');
      await userEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }));
      // Seul le champ modifié part.
      await waitFor(() => expect(sent).toEqual({ start_date: '2025-06-24' }));
      expect(await within(dialog).findByText('du 24/06/2025 au 23/06/2030')).toBeInTheDocument();
      expect(within(dialog).queryByTestId('chronology-edit')).not.toBeInTheDocument();
    });

    it('supprime un passage qui n’existe pas en gardant ses pièces (siège et CEO)', async () => {
      loginAs('u-ceo');
      let url = '';
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, doubled()]))),
        http.delete(`${endpoint}/SN-cardio/pages/amm-1/periods/r2`, ({ request }) => {
          url = request.url;
          return HttpResponse.json(binder([checked, page()]));
        }),
      );
      const dialog = await openChronology();
      // N'importe quel passage se supprime, pas seulement le plus récent.
      expect(within(dialog).getByRole('button', { name: 'Supprimer Renouvellement 1' })).toBeInTheDocument();
      await userEvent.click(within(dialog).getByRole('button', { name: 'Supprimer Renouvellement 2' }));
      // Les pièces vont sur l'AMM d'origine par défaut ; on choisit le renouvellement 1.
      const select = within(dialog).getByLabelText(/1 pièce à ranger sur/);
      expect(select).toHaveTextContent("AMM d'origine");
      await userEvent.click(select);
      await userEvent.click(await screen.findByRole('option', { name: 'Renouvellement 1' }));
      await userEvent.click(within(dialog).getByRole('button', { name: 'Supprimer le passage' }));
      await waitFor(() => expect(new URL(url).searchParams.get('move_to')).toBe('r1'));
    });

    it('un réglementaire pays ne supprime pas de passage', async () => {
      loginAs('u-sn');
      server.use(http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, doubled()]))));
      const dialog = await openChronology();
      expect(within(dialog).queryByRole('button', { name: /^Supprimer Renouvellement/ })).toBeNull();
    });

    it("range une pièce sur une autre période ; seul l'administrateur peut la retirer", async () => {
      loginAs('u-sn');
      let sent: unknown = null;
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, doubled()]))),
        http.patch(`${endpoint}/SN-cardio/pages/amm-1/documents/doc-r2`, async ({ request }) => {
          sent = await request.json();
          return HttpResponse.json(binder([checked, doubled()]));
        }),
      );
      const dialog = await openChronology();
      await userEvent.click(within(dialog).getByLabelText('Corriger la décision du 20/08/2026'));
      expect(within(dialog).queryByRole('button', { name: 'Retirer la pièce' })).toBeNull();
      await userEvent.click(within(dialog).getByLabelText('Période'));
      await userEvent.click(await screen.findByRole('option', { name: 'Renouvellement 1' }));
      await userEvent.click(within(dialog).getByRole('button', { name: 'Enregistrer' }));
      await waitFor(() => expect(sent).toEqual({ period: 'r1' }));
    });

    it("l'administrateur retire une pièce", async () => {
      loginAs('u-ceo');
      let removed = false;
      server.use(
        http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(binder([checked, doubled()]))),
        http.delete(`${endpoint}/SN-cardio/pages/amm-1/documents/doc-r2`, () => {
          removed = true;
          return HttpResponse.json(binder([checked, doubled()]));
        }),
      );
      const dialog = await openChronology();
      await userEvent.click(within(dialog).getByLabelText('Corriger la décision du 20/08/2026'));
      await userEvent.click(within(dialog).getByRole('button', { name: 'Retirer la pièce' }));
      await userEvent.click(within(dialog).getByRole('button', { name: 'Confirmer le retrait' }));
      await waitFor(() => expect(removed).toBe(true));
    });
  });

  it("ajoute la page d'un produit oublié et l'ouvre", async () => {
    loginAs('u-sn');
    const added = page({
      amm_id: 'amm-9',
      page: 2,
      product_name: 'BISOPROLOL GH 5MG',
      original: { number: '19070123', start_date: null, end_date: null },
    });
    let body: unknown = null;
    const after = () => binder([checked, added, page({ page: 3 })]);
    server.use(
      http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json(body ? after() : binder([checked, page()]))),
      http.post(`${endpoint}/SN-cardio/pages`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            amm_id: 'amm-9',
            binder_key: 'SN-cardio',
            product_created: true,
            binder: binder([checked, added, page({ page: 3 })]),
          },
          { status: 201 },
        );
      }),
    );
    renderApp('/classeurs/SN-cardio');
    await userEvent.click(await screen.findByRole('button', { name: 'Ajouter une page' }));
    await userEvent.type(screen.getByLabelText(/Produit \(tel/), 'BISOPROLOL GH 5MG');
    await userEvent.type(screen.getByLabelText("N° d'AMM d'origine"), '19070123');
    await userEvent.click(screen.getByRole('button', { name: 'Ajouter la page' }));
    await waitFor(() =>
      expect(body).toMatchObject({ product_name: 'BISOPROLOL GH 5MG', original_number: '19070123' }),
    );
    const book = screen.getByTestId('binder-book');
    expect(await within(book).findByRole('heading', { name: 'BISOPROLOL GH 5MG' })).toBeInTheDocument();
  });

  it("s'ouvre sur la page demandée et signale ce que le dashboard a changé depuis le constat", async () => {
    loginAs('u-sn');
    const stale = {
      ...checked,
      changed_since_check: [
        { slot: 'original' as const, field: 'start_date' as const, checked: '2010-12-22', now: '2015-12-22' },
      ],
      changed_by: 'import Excel du Dashboard',
      trace: {
        excel: {
          batch_id: 'imp-1',
          date: '2026-09-28T09:00:00Z',
          sheet: 'SENEGAL',
          row: 42,
          outcome: 'UPDATED',
        },
        dossier: null,
      },
    };
    server.use(
      http.get(`${endpoint}/SN-cardio`, () => HttpResponse.json({ ...binder([stale, page()]), stale: 1 })),
    );
    renderApp('/classeurs/SN-cardio?amm=amm-0');
    const book = await screen.findByTestId('binder-book', {}, { timeout: 5000 });
    expect(await within(book).findByRole('heading', { name: 'ACARBOSE GH 100MG' })).toBeInTheDocument();
    const banner = within(book).getAllByTestId('page-stale')[0];
    expect(banner).toHaveTextContent('import Excel du Dashboard');
    expect(banner).toHaveTextContent('22/12/2010');
    expect(within(book).getAllByTestId('page-trace')[0]).toHaveTextContent('feuille SENEGAL, ligne 42');
    expect(screen.getByText('1 à revérifier')).toBeInTheDocument();
  });
});
