import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { DossierImportBatch } from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const endpoint = '/api/v1/dossier-imports';
const file = (id: string, path: string) => ({
  id,
  relative_path: path,
  sha256: id,
  content_type: 'application/pdf',
  size_bytes: 100,
  extraction: {},
  document_id: null,
});
const fixture = (): DossierImportBatch => ({
  id: 'batch-1',
  root_name: 'AMM Produit X',
  status: 'READY',
  preview_token: 'preview-v1',
  created_at: '2026-09-10T09:00:00Z',
  finished_at: '2026-09-10T09:01:00Z',
  error: '',
  amm_id: null,
  auto_applied: false,
  files: [
    file('file-1', 'AMM Produit X/ORIGINE/decision.pdf'),
    file('file-2', 'AMM Produit X/RENOUVELLEMENT_2026/decision_renouvellement.pdf'),
    file('file-3', 'AMM Produit X/ORIGINE/notice.pdf'),
  ],
  audit: [],
  preview: {
    version: 1,
    confidence: 97,
    level: 'HIGH',
    can_apply: true,
    blockers: [],
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
      original_number: 'AMM/SN/2025/00152',
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
        confidence: 97,
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
      {
        id: 'completion-1',
        target: 'amm',
        field: 'holder',
        old: '',
        new: 'Laboratoire X',
        confidence: 97,
        proof_file_id: 'file-1',
        requires_confirmation: false,
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

const appliedSummary = {
  amm_id: 'amm-1',
  product: 'PRODUIT X',
  country: 'Sénégal',
  country_iso2: 'SN',
  number: '9601',
  created: false,
  before: { status: 'EXPIRE', dossier_state: 'INCOMPLET', effective_end_date: '2026-09-15' },
  after: { status: 'VALIDE', dossier_state: 'COMPLET', effective_end_date: '2031-08-20' },
  renewals_created: [{ number: '9601/R1', start_date: '2026-08-20', end_date: '2031-08-20' }],
  fields_changed: [],
  documents: [{ title: 'decision.pdf', kind: 'AMM' as const, period: 'renewal' as const }],
  missing_scan: null,
  lines: ['Statut : Expirée → Valide'],
};

const keep = () => screen.getByRole('button', { name: /^Garder : 11380113/ });
const replace = () => screen.getByRole('button', { name: /^Remplacer par : 12380213/ });

function detail(batch = fixture()) {
  server.use(http.get(`${endpoint}/batch-1`, () => HttpResponse.json(batch)));
  loginAs('u-sn');
  return renderApp('/dossier-imports/batch-1');
}

describe('import intelligent de dossiers AMM', () => {
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
    const file = new File(['%PDF-1.7'], 'decision.pdf', { type: 'application/pdf' });
    Object.defineProperty(file, 'webkitRelativePath', { value: 'AMM/ORIGINE/decision.pdf' });
    fireEvent.change(picker, { target: { files: [file] } });
    await userEvent.click(screen.getByRole('button', { name: 'Analyser le dossier' }));
    await screen.findByText(/Analyse des documents en cours/);
    expect(requests).toHaveLength(1);
    expect(requests[0].get('root_name')).toBe('AMM');
    expect(JSON.parse(requests[0].get('paths') as string)).toEqual(['AMM/ORIGINE/decision.pdf']);
    expect(requests[0].getAll('files')).toHaveLength(1);
  });

  it('montre la chronologie origine puis renouvellement, sans clé technique', async () => {
    detail();
    const origin = await screen.findByTestId('step-1');
    expect(within(origin).getByText('AMM d’origine')).toBeVisible();
    expect(within(origin).getByText('01/01/2021 → 01/01/2026')).toBeVisible();
    expect(within(origin).getByText('À vérifier')).toBeVisible();
    expect(within(origin).getByText(/Sera complété : Titulaire → Laboratoire X/)).toBeVisible();
    const renewal = screen.getByTestId('step-2');
    expect(within(renewal).getByText('Renouvellement du 01/01/2026')).toBeVisible();
    expect(within(renewal).getByText('01/01/2026 → 01/01/2031')).toBeVisible();
    expect(within(renewal).getByText('Sera ajouté')).toBeVisible();
    expect(within(renewal).getByText('En vigueur')).toBeVisible();
    expect(within(renewal).getByRole('button', { name: 'Voir le scan' })).toBeVisible();
    expect(screen.getByText('À vérifier : 1 point')).toBeVisible();
    expect(screen.getByText('À vérifier (1 point)')).toBeVisible();
    // Encadré « Après validation » calculé par le serveur.
    const after = screen.getByRole('region', { name: 'Après validation' });
    expect(within(after).getByText('01/01/2031')).toBeVisible();
    expect(within(after).getByText('Valide')).toBeVisible();
    expect(within(after).getByText(/Dépôt idéal/)).toHaveTextContent('Dépôt idéal : 01/07/2030');
    expect(within(after).getByText(/Limite agence/)).toHaveTextContent('Limite agence : 01/10/2030');
    expect(within(after).getByText(/Dossier complet/)).toBeVisible();
    // La notice n'est pas une preuve d'étape : elle est rangée dans « Autres documents ».
    expect(screen.getByText('Autres documents (1)')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/renewal-/);
  });

  it('traduit les blocages et interdit la validation', async () => {
    const batch = fixture();
    batch.preview!.blockers = [
      'renewal-2026-01-01 : la date de fin précède la date de début.',
      'renewal-unresolved : une décision officielle datée est nécessaire.',
    ];
    batch.preview!.can_apply = false;
    detail(batch);
    expect(
      await screen.findByText(
        'Bloqué : Renouvellement du 01/01/2026 : la date de fin précède la date de début.',
      ),
    ).toBeVisible();
    expect(
      screen.getByText('Renouvellement (date non lue) : une décision officielle datée est nécessaire.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Valider' })).toBeDisabled();
    expect(document.body.textContent).not.toMatch(/renewal-/);
  });

  it('garde la valeur enregistrée par défaut et valide sans correction', async () => {
    const payloads: unknown[] = [];
    const batch = fixture();
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, async ({ request }) => {
        payloads.push(await request.json());
        // Le lot devient appliqué côté serveur : la relecture déclenchée par la confirmation
        // doit renvoyer le même état, sinon l'écran repasserait en « à valider ».
        Object.assign(batch, { status: 'APPLIED', amm_id: 'amm-1', summary: appliedSummary });
        return HttpResponse.json(batch);
      }),
    );
    detail(batch);
    await screen.findByTestId('step-1');
    expect(keep()).toHaveAttribute('aria-pressed', 'true');
    expect(replace()).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Lecture incertaine, vérifiez sur le scan.')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Valider' }));
    await screen.findByText(/Import validé\. Les personnes concernées/);
    expect(screen.getByText('Ce que l’import a changé')).toBeVisible();
    expect(screen.getByText('Expirée')).toBeVisible();
    expect(screen.getByText('Complet')).toBeVisible();
    expect(screen.getByText(/N° 9601\/R1/)).toBeVisible();
    expect(screen.getAllByText('Validé').length).toBeGreaterThan(0);
    expect(payloads).toEqual([{ preview_token: 'preview-v1', accepted_changes: [] }]);
  });

  it('envoie uniquement la correction où « Remplacer » est choisi', async () => {
    const payloads: unknown[] = [];
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, async ({ request }) => {
        payloads.push(await request.json());
        return HttpResponse.json({ ...fixture(), status: 'APPLIED' });
      }),
    );
    detail();
    await screen.findByTestId('step-1');
    await userEvent.click(replace());
    expect(replace()).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/hors remplacements choisis/)).toBeVisible();
    await userEvent.click(keep());
    await userEvent.click(replace());
    await userEvent.click(screen.getByRole('button', { name: 'Valider' }));
    await waitFor(() =>
      expect(payloads).toEqual([{ preview_token: 'preview-v1', accepted_changes: ['correction-1'] }]),
    );
  });

  it('bloque les modifications à faible confiance même si can_apply est incohérent', async () => {
    const batch = fixture();
    batch.preview!.level = 'LOW';
    batch.preview!.confidence = 35;
    detail(batch);
    expect(await screen.findByRole('button', { name: 'Valider' })).toBeDisabled();
    expect(keep()).toBeDisabled();
    expect(replace()).toBeDisabled();
    expect(screen.getByText(/Bloqué : Lecture trop incertaine \(35 %\)/)).toBeVisible();
  });

  it('demande une nouvelle analyse après un conflit et réinitialise les choix', async () => {
    const batch = fixture();
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, () =>
        HttpResponse.json({ detail: 'Prévisualisation périmée.' }, { status: 409 }),
      ),
      http.post(`${endpoint}/batch-1/analyze`, () => {
        batch.preview_token = 'preview-v2';
        return HttpResponse.json(batch);
      }),
    );
    detail(batch);
    await screen.findByTestId('step-1');
    await userEvent.click(replace());
    await userEvent.click(screen.getByRole('button', { name: 'Valider' }));
    await screen.findByText(/Les informations en base ont changé/);
    expect(screen.getByRole('button', { name: 'Valider' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Relancer l’analyse' }));
    await waitFor(() => expect(screen.queryByText(/Les informations en base ont changé/)).toBeNull());
    expect(keep()).toHaveAttribute('aria-pressed', 'true');
  });

  it('conserve l’aperçu et affiche les refus de permission', async () => {
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, () =>
        HttpResponse.json({ detail: 'Vous ne pouvez pas modifier cette AMM.' }, { status: 403 }),
      ),
    );
    detail();
    await userEvent.click(await screen.findByRole('button', { name: 'Valider' }));
    expect(await screen.findByText('Vous ne pouvez pas modifier cette AMM.')).toBeVisible();
    expect(screen.getByTestId('change-correction-1')).toBeVisible();
  });

  it('signale un import validé automatiquement, sur la page et dans l’historique', async () => {
    const auto: DossierImportBatch = {
      ...fixture(),
      status: 'APPLIED',
      auto_applied: true,
      amm_id: 'amm-1',
      summary: appliedSummary,
    };
    const review = { ...fixture(), id: 'batch-2', root_name: 'AMM Produit Y' };
    review.preview = { ...review.preview!, warnings: ['Fichier identique présent plusieurs fois : a.pdf.'] };
    const blocked = { ...fixture(), id: 'batch-3', root_name: 'AMM Produit Z' };
    blocked.preview = { ...blocked.preview!, can_apply: false, blockers: ['Pays non reconnu.'] };
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({ count: 3, next: null, previous: null, results: [auto, review, blocked] }),
      ),
    );
    detail(auto);
    expect(await screen.findByText('Validé automatiquement')).toBeVisible();
    expect(screen.getByText(/Import validé automatiquement/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Valider' })).toBeNull();

    renderApp('/dossier-imports');
    const rows = await screen.findAllByRole('row');
    expect(within(rows[1]).getByText('Validé automatiquement')).toBeVisible();
    expect(within(rows[2]).getByText('À vérifier (2 points)')).toBeVisible();
    expect(within(rows[3]).getByText('Bloqué')).toBeVisible();
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
});
