import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { DossierImportBatch } from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const endpoint = '/api/v1/dossier-imports';
const fixture = (): DossierImportBatch => ({
  id: 'batch-1',
  root_name: 'AMM Produit X',
  status: 'READY',
  preview_token: 'preview-v1',
  created_at: '2026-09-10T09:00:00Z',
  finished_at: '2026-09-10T09:01:00Z',
  error: '',
  amm_id: null,
  files: [
    {
      id: 'file-1',
      relative_path: 'AMM Produit X/ORIGINE/decision.pdf',
      sha256: 'abc',
      content_type: 'application/pdf',
      size_bytes: 100,
      extraction: {},
      document_id: null,
    },
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
    original: { original_number: 'AMM/SN/2025/00152' },
    candidates: [],
    documents: [
      {
        file_id: 'file-1',
        path: 'AMM Produit X/ORIGINE/decision.pdf',
        kind: 'AMM',
        period: 'original',
        document_date: '2025-01-01',
        duplicate_id: null,
      },
    ],
    renewals: [
      {
        key: '2026',
        existing_id: null,
        number: 'REN/2026',
        start_date: '2026-01-01',
        decision_date: '2026-01-01',
        end_date: '2031-01-01',
        confidence: 97,
        proof_file_id: 'file-1',
      },
    ],
    changes: [
      {
        id: 'correction-1',
        target: 'amm',
        field: 'original_number',
        old: 'AMM/SN/2025/00125',
        new: 'AMM/SN/2025/00152',
        confidence: 97,
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
  },
});

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

  it('ne présélectionne aucune correction et permet de valider uniquement les compléments', async () => {
    const payloads: unknown[] = [];
    const batch = fixture();
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, async ({ request }) => {
        payloads.push(await request.json());
        return HttpResponse.json({ ...batch, status: 'APPLIED', amm_id: 'amm-1' });
      }),
    );
    detail(batch);
    const checkbox = await screen.findByRole('checkbox', { name: /Valider la correction Numéro/ });
    expect(checkbox).not.toBeChecked();
    expect(within(screen.getByTestId('change-completion-1')).queryByRole('checkbox')).toBeNull();
    expect(screen.getByText('Créer un renouvellement')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Valider l’import' }));
    await screen.findByText(/Import validé\. Les rattachements/);
    expect(payloads).toEqual([{ preview_token: 'preview-v1', accepted_changes: [] }]);
  });

  it('envoie uniquement la correction explicitement validée', async () => {
    const payloads: unknown[] = [];
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, async ({ request }) => {
        payloads.push(await request.json());
        return HttpResponse.json({ ...fixture(), status: 'APPLIED' });
      }),
    );
    detail();
    await userEvent.click(await screen.findByRole('checkbox', { name: /Valider la correction Numéro/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Valider l’import et 1 correction' }));
    await waitFor(() =>
      expect(payloads).toEqual([{ preview_token: 'preview-v1', accepted_changes: ['correction-1'] }]),
    );
  });

  it('bloque les modifications à faible confiance même si can_apply est incohérent', async () => {
    const batch = fixture();
    batch.preview!.level = 'LOW';
    batch.preview!.confidence = 35;
    detail(batch);
    expect(await screen.findByRole('button', { name: 'Valider l’import' })).toBeDisabled();
    expect(screen.getByRole('checkbox')).toBeDisabled();
    expect(screen.getByText(/Confiance insuffisante/)).toBeVisible();
  });

  it('affiche les blocages serveur et interdit la validation', async () => {
    const batch = fixture();
    batch.preview!.blockers = ['Plusieurs AMM correspondent à ce dossier.'];
    detail(batch);
    expect(await screen.findByText('Plusieurs AMM correspondent à ce dossier.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Valider l’import' })).toBeDisabled();
  });

  it('demande une nouvelle analyse après un conflit et réinitialise les corrections', async () => {
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
    await userEvent.click(await screen.findByRole('checkbox', { name: /Valider la correction Numéro/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Valider l’import et 1 correction' }));
    await screen.findByText(/Les informations en base ont changé/);
    expect(screen.getByRole('button', { name: 'Valider l’import et 1 correction' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Relancer l’analyse' }));
    await waitFor(() => expect(screen.queryByText(/Les informations en base ont changé/)).toBeNull());
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('conserve la prévisualisation et affiche les refus de permission', async () => {
    server.use(
      http.post(`${endpoint}/batch-1/confirm`, () =>
        HttpResponse.json({ detail: 'Vous ne pouvez pas modifier cette AMM.' }, { status: 403 }),
      ),
    );
    detail();
    await userEvent.click(await screen.findByRole('button', { name: 'Valider l’import' }));
    expect(await screen.findByText('Vous ne pouvez pas modifier cette AMM.')).toBeVisible();
    expect(screen.getByTestId('change-correction-1')).toBeVisible();
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
    await userEvent.click((await screen.findAllByRole('button', { name: 'Examiner : decision.pdf' }))[0]);
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
