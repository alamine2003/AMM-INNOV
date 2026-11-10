import type { BinderPage } from '@/api/types';
import CancelIcon from '@mui/icons-material/Cancel';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import { Box, Stack, Typography } from '@mui/material';
import { INK, LINE, MUTED } from './paper';

/** Les 4 niveaux de vérification du dossier, et le résultat (calculé par AMM GH). */

export const VERDICT_COLORS = { CONFORME: '#2e7d32', NON_CONFORME: '#c62828', NON_VERIFIE: MUTED };

/** Les 4 niveaux de vérification du dossier, et le résultat (calculé par AMM GH). */
export function ConformityPanel({ page }: { page: BinderPage }) {
  const { conformity } = page;
  const color = VERDICT_COLORS[conformity.status];
  return (
    <Box
      data-testid="page-conformity"
      sx={{ mt: 1.5, bgcolor: '#fff', border: `1px solid ${LINE}`, borderRadius: 2, p: 1.75 }}
    >
      <Typography sx={{ fontSize: 11, fontWeight: 800, color: MUTED, letterSpacing: 0.6, mb: 1 }}>
        VÉRIFICATION DU DOSSIER
      </Typography>
      <Stack spacing={0.5}>
        {conformity.criteria.map((criterion, index) => (
          <Stack key={criterion.key} direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
            {criterion.ok === true ? (
              <CheckCircleIcon sx={{ fontSize: 18, color: '#2e7d32', mt: '1px' }} aria-label="juste" />
            ) : criterion.ok === false ? (
              <CancelIcon sx={{ fontSize: 18, color: '#c62828', mt: '1px' }} aria-label="à régler" />
            ) : (
              <RadioButtonUncheckedIcon
                sx={{ fontSize: 18, color: MUTED, mt: '1px' }}
                aria-label="à vérifier"
              />
            )}
            <Typography sx={{ fontSize: 13, color: INK }}>
              {index + 1}. {criterion.label}
              <Typography
                component="span"
                sx={{ fontSize: 12, color: criterion.ok === false ? '#c62828' : MUTED }}
              >
                {' '}
                — {criterion.detail}
              </Typography>
            </Typography>
          </Stack>
        ))}
      </Stack>
      <Typography
        data-testid="page-verdict"
        sx={{ mt: 1.25, fontWeight: 900, fontSize: 15, color, letterSpacing: 0.2 }}
      >
        Résultat : {conformity.label}
      </Typography>
    </Box>
  );
}
