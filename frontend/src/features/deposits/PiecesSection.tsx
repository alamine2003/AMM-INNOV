import type { DepositDetail } from '@/api/types';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import { Box, Chip, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type Actions, FileButton, PIECE_ACCEPT, PieceChip, Section, useFail } from './sectionParts';

/** Étape 1 : les pièces du dossier. */

// --- 1. Pièces -----------------------------------------------------------------------------

export function PiecesSection({ dossier, actions }: { dossier: DepositDetail; actions: Actions }) {
  const fail = useFail();
  const { t } = useTranslation();
  const editable = dossier.can.manage;
  const removable = editable && !dossier.sent_at;
  const [otherLabel, setOtherLabel] = useState('');
  const done = dossier.pieces_done >= dossier.pieces_required;
  return (
    <Section
      index={1}
      title={t('deposits.pieces.title')}
      subtitle={`${t('deposits.pieces.subtitle', {
        done: dossier.pieces_done,
        required: dossier.pieces_required,
      })}${dossier.sent_at ? t('deposits.pieces.sentSuffix') : ''}`}
      state={done || dossier.sent_at ? 'done' : 'active'}
      testId="section-pieces"
    >
      <Stack divider={<Box sx={{ borderBottom: 1, borderColor: 'divider' }} />}>
        {dossier.checklist.map(({ piece_type: type, files, done: present }) => (
          <Stack
            key={type.id}
            direction={{ xs: 'column', sm: 'row' }}
            gap={1}
            alignItems={{ sm: 'center' }}
            sx={{ py: 1 }}
            data-testid={`piece-${type.label}`}
          >
            <Stack direction="row" gap={1} alignItems="center" sx={{ flex: '0 0 42%' }}>
              {present ? (
                <CheckCircleIcon color="success" fontSize="small" />
              ) : (
                <RadioButtonUncheckedIcon color={type.required ? 'warning' : 'disabled'} fontSize="small" />
              )}
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {type.label}
                  {!type.required && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {' '}
                      {t('deposits.optional')}
                    </Typography>
                  )}
                  {type.country && <Chip size="small" label={type.country} sx={{ ml: 1, height: 18 }} />}
                </Typography>
                {type.help_text && (
                  <Typography variant="caption" color="text.secondary">
                    {type.help_text}
                  </Typography>
                )}
              </Box>
            </Stack>
            <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ flexGrow: 1, minWidth: 0 }}>
              {files.map((piece) => (
                <PieceChip
                  key={piece.id}
                  dossierId={dossier.id}
                  piece={piece}
                  onDelete={
                    removable ? () => actions.removePiece.mutate(piece.id, { onError: fail }) : undefined
                  }
                />
              ))}
            </Stack>
            {editable && (
              <FileButton
                label={files.length ? t('deposits.pieces.add') : t('deposits.pieces.attach')}
                accept={PIECE_ACCEPT}
                disabled={actions.addPiece.isPending}
                onFile={(file) => actions.addPiece.mutate({ file, piece_type: type.id }, { onError: fail })}
              />
            )}
          </Stack>
        ))}
      </Stack>
      {(dossier.other_pieces.length > 0 || editable) && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="body2" fontWeight={600} gutterBottom>
            {t('deposits.pieces.others')}
          </Typography>
          <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 1 }}>
            {dossier.other_pieces.map((piece) => (
              <Tooltip key={piece.id} title={piece.label}>
                <span>
                  <PieceChip
                    dossierId={dossier.id}
                    piece={piece}
                    onDelete={
                      removable ? () => actions.removePiece.mutate(piece.id, { onError: fail }) : undefined
                    }
                  />
                </span>
              </Tooltip>
            ))}
          </Stack>
          {editable && (
            <Stack direction="row" gap={1} alignItems="center">
              <TextField
                size="small"
                label={t('deposits.pieces.name')}
                placeholder={t('deposits.pieces.namePlaceholder')}
                value={otherLabel}
                onChange={(e) => setOtherLabel(e.target.value)}
              />
              <FileButton
                label={t('deposits.pieces.attach')}
                accept={PIECE_ACCEPT}
                disabled={!otherLabel.trim() || actions.addPiece.isPending}
                onFile={(file) =>
                  actions.addPiece.mutate(
                    { file, label: otherLabel.trim() },
                    { onSuccess: () => setOtherLabel(''), onError: fail },
                  )
                }
              />
            </Stack>
          )}
        </Box>
      )}
    </Section>
  );
}
