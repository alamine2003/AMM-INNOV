import { useState } from 'react';
import { Box, IconButton, LinearProgress, Stack, Tooltip, Typography } from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import VerifiedIcon from '@mui/icons-material/Verified';
import { Link } from 'react-router';
import { useSnackbar } from 'notistack';
import { extractErrorMessage } from '@/api/client';
import { useCurrentUser } from '@/api/hooks/useAuth';
import { fetchBinderPdf, useBinders } from '@/api/hooks/useBinders';
import type { BinderSummary } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { formatDate } from '@/lib/dates';
import { saveBlob } from '@/lib/download';
import { NAVY } from './paper';

/** Dos d'un classeur à levier : étiquette, jauge d'avancement, trou de préhension. */
function Spine({ binder }: { binder: BinderSummary }) {
  const single = binder.sections.length === 1;
  const color = single ? binder.sections[0].color : NAVY;
  const done = binder.total > 0 && binder.checked === binder.total;
  const progress = binder.total ? (binder.checked / binder.total) * 100 : 0;
  return (
    <Box
      component={Link}
      to={`/classeurs/${binder.key}`}
      aria-label={`Ouvrir le classeur ${binder.country_name} — ${binder.title}`}
      data-testid={`spine-${binder.key}`}
      sx={{
        position: 'relative',
        display: 'block',
        width: 78,
        height: 290,
        borderRadius: '6px 6px 3px 3px',
        bgcolor: color,
        backgroundImage:
          'linear-gradient(90deg, rgba(0,0,0,0.28), rgba(255,255,255,0.12) 18%, rgba(255,255,255,0.02) 45%, rgba(0,0,0,0.18) 100%)',
        boxShadow: '3px 0 6px rgba(0,0,0,0.35), inset 0 -6px 0 rgba(0,0,0,0.25)',
        textDecoration: 'none',
        transition: 'transform 180ms ease, box-shadow 180ms ease',
        '&:hover, &:focus-visible': {
          transform: 'translateY(-16px) rotate(-1.5deg)',
          boxShadow: '6px 10px 16px rgba(0,0,0,0.4)',
        },
      }}
    >
      {!single && (
        <Stack sx={{ position: 'absolute', top: 10, left: 8, right: 8, gap: '3px' }}>
          {binder.sections.map((section) => (
            <Box key={section.code} sx={{ height: 5, bgcolor: section.color, borderRadius: 1 }} />
          ))}
        </Stack>
      )}
      <Box
        sx={{
          position: 'absolute',
          top: single ? 16 : 40,
          left: 9,
          right: 9,
          height: 168,
          bgcolor: '#f4efe3',
          borderRadius: 1,
          boxShadow: 'inset 0 0 0 1px #c9bfa8, 0 1px 2px rgba(0,0,0,0.3)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          py: 1,
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            flex: 1,
            writingMode: 'vertical-rl',
            transform: 'rotate(180deg)',
            textAlign: 'center',
            color: '#1d2433',
            lineHeight: 1.1,
          }}
        >
          <Box component="span" sx={{ fontWeight: 900, fontSize: 15, letterSpacing: 0.5 }}>
            {binder.country_name.toUpperCase()}
          </Box>
          <Box component="span" sx={{ display: 'block', fontSize: 11, color: '#6b7280', mt: 0.25 }}>
            {binder.title}
          </Box>
        </Box>
        <Typography sx={{ fontSize: 10, fontWeight: 800, color: '#1d2433', mt: 0.5 }}>
          {binder.checked}/{binder.total}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={progress}
        aria-label="Avancement"
        sx={{
          position: 'absolute',
          left: 12,
          right: 12,
          top: single ? 194 : 218,
          height: 5,
          borderRadius: 3,
          bgcolor: 'rgba(255,255,255,0.25)',
          '& .MuiLinearProgress-bar': { bgcolor: '#7ee081' },
        }}
      />
      {done && (
        <VerifiedIcon
          sx={{
            position: 'absolute',
            top: single ? 206 : 228,
            left: '50%',
            ml: '-11px',
            color: '#7ee081',
            fontSize: 22,
          }}
        />
      )}
      {/* Trou de préhension. */}
      <Box
        sx={{
          position: 'absolute',
          bottom: 20,
          left: '50%',
          width: 30,
          height: 30,
          ml: '-15px',
          borderRadius: '50%',
          bgcolor: 'rgba(0,0,0,0.55)',
          boxShadow: 'inset 2px 3px 5px rgba(0,0,0,0.8), 0 0 0 3px rgba(255,255,255,0.15)',
        }}
      />
    </Box>
  );
}

export default function BindersShelfPage() {
  const shelf = useBinders();
  const user = useCurrentUser();
  const { enqueueSnackbar } = useSnackbar();
  const [downloading, setDownloading] = useState<string | null>(null);
  const isHq = user?.role === 'CEO_ADMIN' || user?.role === 'HQ_REGULATORY';

  const download = async (binder: BinderSummary) => {
    setDownloading(binder.key);
    try {
      saveBlob(await fetchBinderPdf(binder.key), `Classeur_${binder.key}.pdf`);
    } catch (e) {
      enqueueSnackbar(extractErrorMessage(e), { variant: 'error' });
    } finally {
      setDownloading(null);
    }
  };

  const binders = shelf.data ?? [];
  const totals = binders.reduce(
    (acc, b) => ({ pages: acc.pages + b.total, checked: acc.checked + b.checked }),
    { pages: 0, checked: 0 },
  );

  return (
    <Box>
      <PageHeader
        title="Classeurs d'archivage"
        subtitle={
          shelf.data
            ? `${binders.length} classeurs · ${totals.checked} / ${totals.pages} pages vérifiées${
                isHq ? '' : ' · vos pays uniquement'
              }`
            : undefined
        }
      />
      {shelf.isPending ? (
        <LoadingBlock />
      ) : shelf.isError ? (
        <ErrorBlock error={shelf.error} onRetry={() => shelf.refetch()} />
      ) : binders.length === 0 ? (
        <Typography color="text.secondary">Aucun classeur : aucune AMM dans votre périmètre.</Typography>
      ) : (
        <Box
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            rowGap: 5,
            px: { xs: 1, sm: 3 },
            pt: 4,
            pb: 2,
            borderRadius: 3,
            background: 'linear-gradient(180deg, #efe7da, #e4d8c4)',
          }}
        >
          {binders.map((binder) => (
            <Box key={binder.key} sx={{ position: 'relative', px: 1, pt: 2 }}>
              <Tooltip
                placement="top"
                title={
                  <>
                    <b>
                      {binder.country_name} — {binder.title}
                    </b>
                    <br />
                    {binder.checked} / {binder.total} vérifiées · {binder.absent} absentes · {binder.to_scan}{' '}
                    à scanner
                    {binder.last_checked_at && (
                      <>
                        <br />
                        Dernière vérification le {formatDate(binder.last_checked_at)} (
                        {binder.last_checked_by})
                      </>
                    )}
                  </>
                }
              >
                <Box>
                  <Spine binder={binder} />
                </Box>
              </Tooltip>
              {/* Planche de l'étagère. */}
              <Box
                aria-hidden
                sx={{
                  mx: -1,
                  height: 16,
                  background: 'linear-gradient(180deg, #a87945, #7c5430)',
                  boxShadow: '0 8px 10px -4px rgba(60,35,10,0.55)',
                }}
              />
              {isHq && (
                <Tooltip title="Télécharger le classeur en PDF">
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => void download(binder)}
                      disabled={downloading === binder.key}
                      aria-label={`Télécharger le classeur ${binder.country_name} ${binder.title}`}
                      sx={{ display: 'flex', mx: 'auto', mt: 0.5 }}
                    >
                      <DownloadIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
