import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { Amm, DossierImportBatch, DossierReviewPoint } from '@/api/types';
import { db } from '@/mocks/handlers';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const endpoint = '/api/v1/dossier-imports';
const pointsEndpoint = '/api/v1/dossier-review-points';
const file = (id: string, path: string) => ({
  id,
  relative_path: path,
  sha256: id,
  content_type: 'application/pdf',
  size_bytes: 100,
  extraction: {},
  document_id: null,
});

const point = (overrides: Partial<DossierReviewPoint> = {}): DossierReviewPoint => ({
  id: 'point-1',
  batch_id: 'batch-1',
  batch_name: 'AMM Produit X',
  amm_id: 'amm-1',
  renewal_id: null,
  code: 'value_mismatch',
  field: 'original_number',
  message: 'N° d’AMM (AMM d’origine) : la fiche indique « 11380113 », le scan indique « 12380213 ».',
  recorded_value: '11380113',
  scan_value: '12380213',
  proof_file_id: 'file-1',
  proof_name: 'decision.pdf',
  proof_content_type: 'application/pdf',
  confidence: 80,
  applicable: true,
  status: 'OPEN',
  resolved_by_email: null,
  resolved_at: null,
  created_at: '2026-09-10T09:01:00Z',
  ...overrides,
});

const summary = {
  amm_id: 'amm-1',
  product: 'Produit X',
  country: 'Sénégal',
  country_iso2: 'SN',
  number: '11380113',
  created: false,
  before: { status: 'EXPIRE', dossier_state: 'INCOMPLET', effective_end_date: '2026-01-01' },
  after: { status: 'VALIDE', dossier_state: 'COMPLET', effective_end_date: '2031-01-01' },
  renewals_created: [{ number: 'REN/2026', start_date: '2026-01-01', end_date: '2031-01-01' }],
  fields_changed: [],
  documents: [{ title: 'decision.pdf', kind: 'AMM', period: 'renewal' as const }],
  missing_scan: null,
  review_points: 1,
  lines: ['Statut : Expirée → Valide'],
};

/** Lot rangé automatiquement : origine + renouvellement créé, un écart gardé en point. */
const fixture = (): DossierImportBatch => ({
  id: 'batch-1',
  root_name: 'AMM Produit X',
  status: 'APPLIED',
  auto_applied: true,
  preview_token: 'preview-v1',
  created_at: '2026-09-10T09:00:00Z',
  finished_at: '2026-09-10T09:01:00Z',
  error: '',
  amm_id: 'amm-1',
  files: [
    file('file-1', 'AMM Produit X/ORIGINE/decision.pdf'),
    file('file-2', 'AMM Produit X/RENOUVELLEMENT_2026/decision_renouvellement.pdf'),
    file('file-3', 'AMM Produit X/ORIGINE/notice.pdf'),
  ],
  audit: [],
  summary,
  review_points: [
    point(),
    point({
      id: 'point-2',
      code: 'reading',
      field: '',
      applicable: false,
      message: 'notice.pdf : document trop long, lu en partie ; vérifiez ses informations sur le scan.',
    }),
  ],
  open_points_count: 2,
  preview: {
    version: 2,
    confidence: 83,
    level: 'MEDIUM',
    can_apply: true,
    blockers: [],
    question: null,
    review_points: [],
    warnings: [],
    amm: {
      id: 'amm-1',
      product_id: 'product-1',
      product_name: 'Produit X',
      country_id: 'country-sn',
      country_iso2: 'SN',
      holder: 'Laboratoire X',
    },
    original: {
      original_number: '12380213',
      original_start_date: '2021-01-01',
      original_end_date: '2026-01-01',
    },
    candidates: [],
    documents: [
      {
        file_id: 'file-1',
        path: 'AMM Produit X/ORIGINE/decision.pdf',
        kind: 'AMM',
        period: 'original',
        document_date: '2021-01-01',
        duplicate_id: null,
      },
      {
        file_id: 'file-2',
        path: 'AMM Produit X/RENOUVELLEMENT_2026/decision_renouvellement.pdf',
        kind: 'AMM',
        period: 'renewal-2026-01-01',
        document_date: '2026-01-01',
        duplicate_id: null,
      },
      {
        file_id: 'file-3',
        path: 'AMM Produit X/ORIGINE/notice.pdf',
        kind: 'AUTRE',
        period: 'original',
        document_date: null,
        duplicate_id: null,
      },
    ],
    renewals: [
      {
        key: 'renewal-2026-01-01',
        existing_id: null,
        number: 'REN/2026',
        start_date: '2026-01-01',
        decision_date: '2026-01-01',
        end_date: '2031-01-01',
        confidence: 83,
        proof_file_id: 'file-2',
      },
    ],
    changes: [
      {
        id: 'correction-1',
        target: 'amm',
        field: 'original_number',
        old: '11380113',
        new: '12380213',
        confidence: 80,
        proof_file_id: 'file-1',
        requires_confirmation: true,
      },
    ],
    projection: {
      effective_end_date: '2031-01-01',
      ideal_filing_date: '2030-07-01',
      agency_filing_deadline: '2030-10-01',
      status: 'VALIDE',
      dossier_state: 'COMPLET',
      missing_scan: null,
      includes_corrections: false,
      timeline: [
        {
          key: 'original',
          existing_id: null,
          number: '11380113',
          start_date: '2021-01-01',
          end_date: '2026-01-01',
          in_force: false,
        },
        {
          key: 'renewal-2026-01-01',
          existing_id: null,
          number: 'REN/2026',
          start_date: '2026-01-01',
          end_date: '2031-01-01',
          in_force: true,
        },
      ],
    },
  },
});

/** Lot dont l'AMM n'est pas identifiable : la seule question posée. */
const questionFixture = (): DossierImportBatch => {
  const batch = fixture();
  return {
    ...batch,
    id: 'batch-q',
    root_name: 'DOSSIER RECU',
    status: 'QUESTION',
    auto_applied: false,
    amm_id: null,
    summary: {},
    review_points: [],
    open_points_count: 0,
    preview: {
      ...batch.preview!,
      can_apply: false,
      blockers: ['Produit « PRODUIT INCONNU 5MG » absent du catalogue.'],
      question: {
        reasons: ['Produit « PRODUIT INCONNU 5MG » absent du catalogue.'],
        codes: ['product_absent'],
        can_create: false,
      },
      amm: { ...batch.preview!.amm, id: null, product_id: null, product_name: 'PRODUIT INCONNU 5MG' },
    },
  };
};

function detail(batch = fixture()) {
  server.use(http.get(`${endpoint}/${batch.id}`, () => HttpResponse.json(batch)));
  loginAs('u-sn');
  return renderApp(`/dossier-imports/${batch.id}`);
}

describe('import automatique de dossiers AMM', () => {
  it('reste accessible au réglementaire pays et envoie les chemins du dossier sélectionné', async () => {
    const requests: FormData[] = [];
    server.use(
      http.get(endpoint, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
      http.post(endpoint, async ({ request }) => {
        requests.push(await request.formData());
        return HttpResponse.json({ ...fixture(), status: 'PENDING' }, { status: 202 });
      }),
      http.get(`${endpoint}/batch-1`, () => HttpResponse.json({ ...fixture(), status: 'PENDING' })),
    );
    loginAs('u-sn');
    renderApp('/dossier-imports');
    const picker = await screen.findByLabelText('Dossier AMM');
    expect(picker).toHaveAttribute('webkitdirectory');
    const upload = new File(['%PDF-1.7'], 'decision.pdf', { type: 'application/pdf' });
    Object.defineProperty(upload, 'webkitRelativePath', { value: 'AMM/ORIGINE/decision.pdf' });
    fireEvent.change(picker, { target: { files: [upload] } });
    await userEvent.click(screen.getByRole('button', { name: 'Analyser le dossier' }));
    expect(await screen.findByText('Analyse en cours…')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0].get('root_name')).toBe('AMM');
    expect(JSON.parse(requests[0].get('paths') as string)).toEqual(['AMM/ORIGINE/decision.pdf']);
    expect(requests[0].getAll('files')).toHaveLength(1);
  });

  it('affiche « Rangé automatiquement », la frise et le résultat, sans rien à arbitrer', async () => {
    detail();
    expect(await screen.findByTestId('batch-state')).toHaveTextContent('Rangé automatiquement');
    const origin = screen.getByTestId('step-1');
    expect(within(origin).getByText('AMM d’origine')).toBeVisible();
    expect(within(origin).getByText('01/01/2021 → 01/01/2026')).toBeVisible();
    expect(within(origin).getByRole('button', { name: 'Voir le scan' })).toBeVisible();
    const renewal = screen.getByTestId('step-2');
    expect(within(renewal).getByText('Renouvellement du 01/01/2026')).toBeVisible();
    expect(within(renewal).getByText('Ajouté par ce dossier')).toBeVisible();
    expect(within(renewal).getByText('En vigueur')).toBeVisible();
    const result = screen.getByRole('region', { name: 'Résultat' });
    expect(within(result).getByText('Valide')).toBeVisible();
    expect(within(result).getByText('01/01/2031')).toBeVisible();
    expect(within(result).getByText(/la décision en vigueur a son scan/)).toBeVisible();
    // Plus d'arbitrage : ni « Garder / Remplacer », ni bouton « Valider », ni fiabilité en avant.
    expect(screen.queryByRole('button', { name: /Garder|Remplacer|Valider/ })).toBeNull();
    expect(screen.getByText(/Fiabilité de la lecture/)).not.toBeVisible();
    expect(screen.getAllByText('Rangé').length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/renewal-/);
  });

  it('applique la valeur du scan ou ignore un point à vérifier plus tard', async () => {
    const actions: string[] = [];
    server.use(
      http.post(`${pointsEndpoint}/:id/:action`, ({ params }) => {
        actions.push(`${params.id}:${params.action}`);
        return HttpResponse.json(point({ id: String(params.id), status: 'APPLIED' }));
      }),
    );
    detail();
    const list = await screen.findByRole('region', { name: 'Points à vérifier plus tard' });
    expect(within(list).getByText('Points à vérifier plus tard (2)')).toBeVisible();
    expect(
      within(list).getByText(/la fiche indique « 11380113 », le scan indique « 12380213 »/),
    ).toBeVisible();
    const mismatch = within(list).getByTestId('point-point-1');
    await userEvent.click(within(mismatch).getByRole('button', { name: 'Appliquer la valeur du scan' }));
    const doubt = within(list).getByTestId('point-point-2');
    // Un simple doute de lecture n'a pas de valeur à appliquer : on peut seulement l'ignorer.
    expect(within(doubt).queryByRole('button', { name: 'Appliquer la valeur du scan' })).toBeNull();
    await userEvent.click(within(doubt).getByRole('button', { name: 'Ignorer' }));
    await waitFor(() => expect(actions).toEqual(['point-1:apply', 'point-2:ignore']));
  });

  it('pose une seule question « c’est quelle AMM ? » et range sur l’AMM choisie', async () => {
    const searches: URLSearchParams[] = [];
    const chosen: unknown[] = [];
    const amm = { ...db.amms.find((a) => a.country_iso2 === 'SN')! } as Amm;
    const batch = questionFixture();
    server.use(
      http.get('/api/v1/amms', ({ request }) => {
        searches.push(new URL(request.url).searchParams);
        return HttpResponse.json({ count: 1, next: null, previous: null, results: [amm] });
      }),
      http.post(`${endpoint}/batch-q/choose-amm`, async ({ request }) => {
        chosen.push(await request.json());
        Object.assign(batch, { status: 'PENDING' });
        return HttpResponse.json(batch, { status: 202 });
      }),
    );
    detail(batch);
    expect(await screen.findByTestId('batch-state')).toHaveTextContent('Question : c’est quelle AMM ?');
    expect(screen.getByText(/absent du catalogue/)).toBeVisible();
    // Une seule question : pas de frise ni de résultat tant que l'AMM n'est pas connue.
    expect(screen.queryByTestId('step-1')).toBeNull();
    const button = screen.getByRole('button', { name: 'Ranger les documents ici' });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByLabelText('AMM (recherche par produit)'));
    await userEvent.click(await screen.findByRole('option', { name: new RegExp(amm.product_name) }));
    await userEvent.click(button);
    await waitFor(() => expect(chosen).toEqual([{ amm_id: amm.id }]));
    // Recherche limitée au pays du dossier.
    expect(searches.at(-1)?.get('country')).toBe('SN');
    expect(await screen.findByText('Analyse en cours…')).toBeVisible();
  });

  it('résume chaque lot dans l’historique : AMM, résultat et points à vérifier', async () => {
    const ranged = fixture();
    const question = questionFixture();
    const running = { ...fixture(), id: 'batch-r', root_name: 'EN COURS', status: 'RUNNING' as const };
    running.summary = {};
    running.open_points_count = 0;
    const failed = { ...questionFixture(), id: 'batch-f', root_name: 'ECHEC', status: 'FAILED' as const };
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({
          count: 4,
          next: null,
          previous: null,
          results: [ranged, question, running, failed],
        }),
      ),
    );
    loginAs('u-sn');
    renderApp('/dossier-imports');
    const rows = await screen.findAllByRole('row');
    expect(within(rows[0]).getByText('Points à vérifier')).toBeVisible();
    expect(within(rows[1]).getByText('Rangé')).toBeVisible();
    expect(within(rows[1]).getByRole('link', { name: 'Produit X (SN)' })).toBeVisible();
    expect(within(rows[1]).getByLabelText('2 point(s) à vérifier')).toBeVisible();
    expect(within(rows[2]).getByText('Question')).toBeVisible();
    expect(within(rows[2]).getByText('À préciser')).toBeVisible();
    expect(within(rows[3]).getByText('Analyse en cours')).toBeVisible();
    expect(within(rows[4]).getByText('Échec')).toBeVisible();
  });

  it('affiche l’historique quand un lot vient d’être envoyé (aperçu encore vide)', async () => {
    const fresh = {
      ...fixture(),
      id: 'batch-new',
      root_name: 'CAMEROUN - GRIPEX',
      status: 'PENDING' as const,
    };
    fresh.summary = {};
    fresh.open_points_count = 0;
    (fresh as { preview: unknown }).preview = {};
    server.use(
      http.get(endpoint, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [fresh] })),
    );
    loginAs('u-sn');
    renderApp('/dossier-imports');
    expect(await screen.findByText('CAMEROUN - GRIPEX')).toBeVisible();
    expect(screen.queryByText(/Unexpected Application Error/)).toBeNull();
  });

  it('dit clairement qu’un scan est perdu au lieu d’une erreur serveur', async () => {
    server.use(
      http.get(`${endpoint}/batch-1/file`, () =>
        HttpResponse.json({ detail: 'gone', code: 'file_lost' }, { status: 410 }),
      ),
    );
    detail();
    const origin = await screen.findByTestId('step-1');
    await userEvent.click(within(origin).getByRole('button', { name: 'Voir le scan' }));
    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(
        'Fichier perdu (stocké avant la mise en place du stockage permanent) : réimportez ce dossier.',
      ),
    ).toBeVisible();
    expect(within(dialog).queryByText(/Erreur serveur/)).toBeNull();
  });

  it('charge une preuve avec authentification et libère son URL à la fermeture', async () => {
    const auth: (string | null)[] = [];
    const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:proof');
    const revokeUrl = vi.spyOn(URL, 'revokeObjectURL');
    server.use(
      http.get(`${endpoint}/batch-1/file`, ({ request }) => {
        auth.push(request.headers.get('Authorization'));
        return new HttpResponse('%PDF-1.7', { headers: { 'Content-Type': 'application/pdf' } });
      }),
    );
    detail();
    const origin = await screen.findByTestId('step-1');
    await userEvent.click(within(origin).getAllByRole('button', { name: 'Voir le scan' })[0]);
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('button', { name: 'Télécharger le document' })).toBeEnabled(),
    );
    expect(auth).toEqual(['Bearer mock-access-u-sn']);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Fermer' }));
    await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith('blob:proof'));
    createUrl.mockRestore();
    revokeUrl.mockRestore();
  });

  it('montre les points à vérifier sur la fiche AMM, avec appliquer et ignorer', async () => {
    const amm = db.amms.find((a) => a.country_iso2 === 'SN')!;
    const actions: string[] = [];
    server.use(
      http.get(pointsEndpoint, ({ request }) => {
        const params = new URL(request.url).searchParams;
        expect(params.get('amm')).toBe(amm.id);
        expect(params.get('status')).toBe('OPEN');
        return HttpResponse.json([point({ amm_id: amm.id })]);
      }),
      http.post(`${pointsEndpoint}/:id/:action`, ({ params }) => {
        actions.push(String(params.action));
        return HttpResponse.json(point({ status: 'IGNORED' }));
      }),
    );
    loginAs('u-sn');
    renderApp(`/amms/${amm.id}`);
    const list = await screen.findByRole('region', { name: 'Points à vérifier plus tard' });
    expect(within(list).getByText(/Dossier « AMM Produit X »/)).toBeVisible();
    expect(within(list).getByRole('button', { name: 'Voir le scan' })).toBeVisible();
    await userEvent.click(within(list).getByRole('button', { name: 'Ignorer' }));
    await waitFor(() => expect(actions).toEqual(['ignore']));
  });
});
