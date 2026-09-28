import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { DepositDetail, DepositSuggestion, PieceType } from '@/api/types';
import { server } from '@/mocks/server';
import { loginAs, renderApp } from '@/test/utils';

const api = '/api/v1/deposits';

function pieceType(label: string, overrides: Partial<PieceType> = {}): PieceType {
  return {
    id: `pt-${label.length}`,
    label,
    help_text: '',
    required: true,
    order: 10,
    country: null,
    excluded_countries: [],
    active: true,
    ...overrides,
  };
}

const amm = {
  id: 'amm-1',
  product_name: 'AMLODIPINE GH 5MG CPR B/30',
  range_code: 'CARDIO',
  country_iso2: 'SN',
  country_name: 'Sénégal',
  authority: 'ARP',
  original_number: 'AMM/SN/2021/0152',
  status: 'A_RENOUVELER' as const,
  urgency: 'DEPOT_URGENT',
  effective_end_date: '2027-02-01',
  ideal_filing_date: '2026-08-01',
  agency_filing_deadline: '2026-11-01',
};

function dossier(overrides: Partial<DepositDetail> = {}): DepositDetail {
  return {
    id: 'dep-1',
    stage: 'MONTAGE',
    stage_label: 'Montage du dossier',
    amm,
    renewal: {
      id: 'ren-1',
      sequence: 2,
      workflow_status: 'EN_PREPARATION',
      filing_date: null,
      decision_date: null,
      number: '',
    },
    pieces_done: 0,
    pieces_required: 1,
    samples_required: true,
    samples_count: 0,
    sent_at: null,
    sent_by: null,
    deposited_at: null,
    events_count: 0,
    messages_count: 0,
    last_message_at: null,
    updated_at: '2026-09-28T10:00:00Z',
    send_note: '',
    checklist: [{ piece_type: pieceType('RCP'), files: [], done: false }],
    other_pieces: [],
    samples: [],
    events: [],
    messages: [],
    activities: [
      {
        id: 'a1',
        kind: 'CREE',
        text: 'Dossier ouvert par Siège',
        user: 'Siège',
        created_at: '2026-09-28T09:00:00Z',
      },
    ],
    missing: ['RCP', 'Échantillons (n° de lot, date de fabrication, date de péremption)'],
    attestation: null,
    downloads: [],
    can: { manage: true, deposit: true, follow: false, decide: false },
    ...overrides,
  };
}

const complete = dossier({
  pieces_done: 1,
  samples_count: 1,
  checklist: [
    {
      piece_type: pieceType('RCP'),
      files: [
        {
          id: 'p1',
          piece_type: 'pt-3',
          label: 'RCP',
          filename: 'rcp.docx',
          content_type: '',
          size_bytes: 2048,
          uploaded_by: 'Siège',
          uploaded_at: '2026-09-28T10:00:00Z',
        },
      ],
      done: true,
    },
  ],
  samples: [
    {
      id: 's1',
      batch_number: 'L2409',
      manufactured_on: '2026-03-01',
      expires_on: '2029-02-28',
      quantity: 3,
      note: '',
    },
  ],
  missing: [],
});

describe('Dépôts AMM', () => {
  it('le siège monte le dossier d’une AMM à renouveler depuis « À préparer »', async () => {
    loginAs('u-hq');
    const suggestion: DepositSuggestion = { ...amm, renewal_status: null };
    let opened: unknown = null;
    server.use(
      http.get(api, () => HttpResponse.json([])),
      http.get(`${api}/suggestions`, () => HttpResponse.json([suggestion])),
      http.post(api, async ({ request }) => {
        opened = await request.json();
        return HttpResponse.json(dossier(), { status: 201 });
      }),
      http.get(`${api}/dep-1`, () => HttpResponse.json(dossier())),
    );
    renderApp('/depots');
    expect(await screen.findByText(/À préparer : 1 AMM/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Monter le dossier' }));
    await waitFor(() => expect(opened).toEqual({ amm: 'amm-1' }));
    expect(await screen.findByTestId('section-pieces')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Envoyer au pays/ })).toBeDisabled();
    expect(screen.getByText(/Avant l’envoi/).closest('[role="alert"]')).toHaveTextContent('RCP');
  });

  it('joint une pièce puis envoie le dossier complet au pays', async () => {
    loginAs('u-hq');
    let uploaded: FormData | null = null;
    let sent: unknown = null;
    server.use(
      http.get(`${api}/dep-1`, () => HttpResponse.json(dossier())),
      http.post(`${api}/dep-1/pieces`, async ({ request }) => {
        uploaded = await request.formData();
        return HttpResponse.json(complete, { status: 201 });
      }),
      http.post(`${api}/dep-1/send`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          ...complete,
          stage: 'ENVOYE',
          sent_at: '2026-09-28T11:00:00Z',
          sent_by: 'Siège',
        });
      }),
    );
    renderApp('/depots/dep-1');
    const row = await screen.findByTestId('piece-RCP');
    const file = new File(['rcp'], 'rcp.docx');
    await userEvent.upload(within(row).getByLabelText('Joindre'), file);
    await waitFor(() => expect(uploaded?.get('piece_type')).toBe('pt-3'));
    expect(await screen.findByText(/rcp.docx/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Message au pays/), 'Échantillons par DHL');
    await userEvent.click(screen.getByRole('button', { name: /Envoyer au pays/ }));
    await waitFor(() => expect(sent).toEqual({ note: 'Échantillons par DHL' }));
    expect(await screen.findByText(/Envoyé le/)).toBeInTheDocument();
  });

  it('le pays envoie l’attestation de dépôt et écrit au siège', async () => {
    loginAs('u-sn');
    const sentToCountry = {
      ...complete,
      stage: 'ENVOYE' as const,
      stage_label: 'Envoyé au pays',
      sent_at: '2026-09-28T11:00:00Z',
      sent_by: 'Siège',
      can: { manage: false, deposit: true, follow: false, decide: false },
    };
    let deposit: FormData | null = null;
    let message: unknown = null;
    server.use(
      http.get(`${api}/dep-1`, () => HttpResponse.json(sentToCountry)),
      http.post(`${api}/dep-1/deposit`, async ({ request }) => {
        deposit = await request.formData();
        return HttpResponse.json({
          ...sentToCountry,
          stage: 'DEPOSE',
          renewal: { ...sentToCountry.renewal, workflow_status: 'DEPOSE', filing_date: '2026-09-27' },
          attestation: { id: 'doc-1', document_date: '2026-09-27', filename: 'SN_ATTESTATION.pdf' },
          can: { manage: false, deposit: true, follow: true, decide: true },
        });
      }),
      http.post(`${api}/dep-1/messages`, async ({ request }) => {
        message = await request.json();
        return HttpResponse.json(
          {
            ...sentToCountry,
            messages: [
              {
                id: 'm1',
                author: 'Fatou',
                from_hq: false,
                mine: true,
                body: 'Déposé ce matin.',
                created_at: '2026-09-28T12:00:00Z',
              },
            ],
          },
          { status: 201 },
        );
      }),
    );
    renderApp('/depots/dep-1');
    expect(await screen.findByText(/À faire :/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Envoyer au pays/ })).not.toBeInTheDocument();
    const section = screen.getByTestId('section-deposit');
    const date = within(section).getByLabelText('Date de dépôt');
    await userEvent.clear(date);
    await userEvent.type(date, '2026-09-27');
    await userEvent.upload(
      within(section).getByLabelText(/Attestation de dépôt/),
      new File(['%PDF'], 'attestation.pdf', { type: 'application/pdf' }),
    );
    await userEvent.click(within(section).getByRole('button', { name: /Envoyer l’attestation au siège/ }));
    await waitFor(() => expect(deposit?.get('filing_date')).toBe('2026-09-27'));
    expect(await screen.findByText(/Déposé à ARP le 27\/09\/2026/)).toBeInTheDocument();
    expect(screen.getByTestId('section-follow')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Votre message'), 'Déposé ce matin.');
    await userEvent.click(screen.getByRole('button', { name: 'Envoyer le message' }));
    await waitFor(() => expect(message).toEqual({ body: 'Déposé ce matin.' }));
    expect(await within(screen.getByTestId('messages')).findByText('Déposé ce matin.')).toBeInTheDocument();
  });
});
