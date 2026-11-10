import type { BinderPage } from '@/api/types';
import { formatDate } from '@/lib/dates';
import { Box, Link as MuiLink, Typography } from '@mui/material';
import { Link } from 'react-router';
import { MUTED } from './paper';

/** Habillage papier de la page (pochette, coin plié) et traces des derniers imports. */

/** Pochette plastique transparente : reflets et bord soudé. */
export function Sleeve() {
  return (
    <Box
      aria-hidden
      sx={{
        position: 'absolute',
        inset: 0,
        zIndex: 1,
        pointerEvents: 'none',
        border: '5px solid rgba(255,255,255,0.55)',
        boxShadow: 'inset 0 0 0 1px rgba(150,170,200,0.35)',
        background:
          'linear-gradient(115deg, rgba(255,255,255,0.38) 0%, rgba(255,255,255,0.06) 22%, transparent 34%, ' +
          'rgba(255,255,255,0.16) 55%, transparent 68%, rgba(255,255,255,0.12) 88%, transparent 100%)',
      }}
    />
  );
}

export function FoldedCorner() {
  return (
    <Box
      aria-hidden
      sx={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        zIndex: 2,
        width: 40,
        height: 40,
        pointerEvents: 'none',
        background: 'linear-gradient(45deg, #e6dcc4 0 50%, #d7c8a3 50% 100%)',
        boxShadow: '3px -3px 5px rgba(0,0,0,0.18)',
        borderTopRightRadius: 4,
      }}
    />
  );
}

/** D'où viennent les valeurs de la page : ligne du Dashboard AMM Afrique et dossier importé. */
export function PageTrace({ page }: { page: BinderPage }) {
  const { excel, dossier } = page.trace;
  if (!excel && !dossier) return null;
  return (
    <Typography sx={{ fontSize: 11.5, color: MUTED, mt: 1 }} data-testid="page-trace">
      {excel && (
        <>
          Dashboard AMM Afrique : feuille {excel.sheet}, ligne {excel.row} (
          <MuiLink component={Link} to={`/imports/${excel.batch_id}`}>
            import du {formatDate(excel.date)}
          </MuiLink>
          )
        </>
      )}
      {excel && dossier && ' · '}
      {dossier && (
        <>
          Dossier importé le{' '}
          <MuiLink component={Link} to={`/dossier-imports/${dossier.batch_id}`}>
            {formatDate(dossier.date)}
          </MuiLink>
          {dossier.auto_applied ? ' (rangé automatiquement)' : ''}
        </>
      )}
    </Typography>
  );
}
