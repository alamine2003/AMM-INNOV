import { FitToPage } from './FitToPage';
import { useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  IconButton,
  LinearProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { extractErrorMessage } from '@/api/client';
import { useCan } from '@/features/auth/authStore';
import { useExtraPages } from '@/api/hooks/useBinders';
import type { BinderDetail, BinderPage, BinderSectionSummary } from '@/api/types';
import { formatDateTime } from '@/lib/dates';
import { Flag } from './Flag';
import { Holes, INK, LINE, MUTED, NAVY, Pill, paperSx, tint } from './paper';

function Tile({ value, label }: { value: number; label: string }) {
  return (
    <Box sx={{ flex: '1 1 90px', bgcolor: '#fff', border: `1px solid ${LINE}`, borderRadius: 2, p: 1.25 }}>
      <Typography sx={{ fontSize: 22, fontWeight: 900, lineHeight: 1.1 }}>{value}</Typography>
      <Typography sx={{ fontSize: 12, color: MUTED }}>{label}</Typography>
    </Box>
  );
}

/** Page de garde : l'avancement du classeur et où reprendre. */
export function TitleLeaf({
  binder,
  onResume,
  resumeLabel,
}: {
  binder: BinderDetail;
  onResume: () => void;
  resumeLabel: string | null;
}) {
  const { t } = useTranslation();
  const progress = binder.total ? Math.round((binder.checked / binder.total) * 100) : 0;
  return (
    <Box sx={{ ...paperSx, bgcolor: '#f4efe3' }}>
      <Holes />
      <FitToPage sx={{ pl: 7, pr: 4, py: 3 }}>
        <Typography sx={{ fontSize: 12, fontWeight: 800, color: MUTED, letterSpacing: 1 }}>
          {t('binders.leaves.cover')}
        </Typography>
        <Stack direction="row" alignItems="center" gap={1.5} sx={{ mt: 1 }}>
          <Flag iso2={binder.country_iso2} width={48} />
          <Typography component="h2" sx={{ fontSize: 34, fontWeight: 900, color: INK, lineHeight: 1.1 }}>
            {binder.country_name}
          </Typography>
        </Stack>
        <Typography sx={{ fontSize: 20, color: INK, mb: 1.5 }}>{binder.title}</Typography>
        <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 2 }}>
          {binder.sections.map((section) => (
            <Pill key={section.code} color={section.color}>
              {section.label} · {section.total}
            </Pill>
          ))}
        </Stack>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Tile value={binder.total} label={t('binders.leaves.pages')} />
          <Tile value={binder.checked} label={t('binders.leaves.checked')} />
          <Tile value={binder.conformes} label={t('binders.leaves.conform')} />
          <Tile value={binder.non_conformes} label={t('binders.leaves.nonConform')} />
          <Tile value={binder.absent} label={t('binders.leaves.absent')} />
          <Tile value={binder.to_scan} label={t('binders.leaves.toScan')} />
          <Tile value={binder.to_print} label={t('binders.leaves.toPrint')} />
          {binder.stale > 0 && <Tile value={binder.stale} label={t('binders.leaves.toRecheck')} />}
          <Tile value={binder.extras} label={t('binders.leaves.extra')} />
        </Stack>
        <Box sx={{ mt: 2 }}>
          <LinearProgress
            variant="determinate"
            value={progress}
            color="success"
            sx={{ height: 8, borderRadius: 4 }}
          />
          <Typography sx={{ fontSize: 12, color: MUTED, mt: 0.5 }}>
            {t('binders.leaves.progressChecked', { progress })}
            {binder.last_checked_at
              ? ` · ${t('binders.leaves.lastCheck', {
                  date: formatDateTime(binder.last_checked_at),
                  by: binder.last_checked_by ?? '—',
                })}`
              : ''}
          </Typography>
        </Box>
        {resumeLabel && (
          <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={onResume} sx={{ mt: 2.5 }}>
            {t('binders.leaves.resume', { label: resumeLabel })}
          </Button>
        )}
        <Typography sx={{ fontSize: 12, color: MUTED, mt: 2.5, lineHeight: 1.7 }}>
          <Trans i18nKey="binders.leaves.howTo" components={{ b: <b /> }} />
        </Typography>
      </FitToPage>
    </Box>
  );
}

/** Intercalaire de gamme : carton de couleur avec l'avancement de la gamme. */
export function DividerLeaf({ section, pages }: { section: BinderSectionSummary; pages: BinderPage[] }) {
  const { t } = useTranslation();
  const progress = section.total ? (section.checked / section.total) * 100 : 0;
  return (
    <Box
      sx={{
        ...paperSx,
        bgcolor: tint(section.color, 0.72),
        backgroundImage: 'linear-gradient(90deg, rgba(0,0,0,0.06), transparent 5%)',
      }}
    >
      <Holes />
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{ position: 'absolute', inset: 0, pl: 5, pr: 2, textAlign: 'center' }}
      >
        <Typography
          sx={{ fontSize: { xs: 40, sm: 58 }, fontWeight: 900, color: section.color, letterSpacing: 1 }}
        >
          {section.label.toUpperCase()}
        </Typography>
        <Typography sx={{ fontSize: 18, color: INK, mt: 1 }}>
          {t('binders.leaves.dividerStats', {
            label: section.label,
            checked: section.checked,
            total: section.total,
            count: section.conformes,
          })}
        </Typography>
        <Box sx={{ width: 260, maxWidth: '80%', mt: 2 }}>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{
              height: 8,
              borderRadius: 4,
              bgcolor: 'rgba(255,255,255,0.7)',
              '& .MuiLinearProgress-bar': { bgcolor: section.color },
            }}
          />
        </Box>
        {pages.length > 0 && (
          <Typography sx={{ fontSize: 13, color: MUTED, mt: 2 }}>
            {t('binders.leaves.fromTo', {
              from: pages[0].product_name,
              to: pages[pages.length - 1].product_name,
            })}
          </Typography>
        )}
        {!!section.stale && (
          <Typography sx={{ fontSize: 13, color: '#e65100', fontWeight: 700, mt: 1 }}>
            {t('binders.leaves.staleNote', { n: section.stale })}
          </Typography>
        )}
        {section.absent + section.to_scan > 0 && (
          <Typography sx={{ fontSize: 13, color: INK, mt: 1 }}>
            {t('binders.leaves.absentToScan', { absent: section.absent, toScan: section.to_scan })}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

/** Dernière feuille : bilan, pages en trop (dossiers sans AMM) et téléchargement du siège. */
export function EndLeaf({
  binder,
  onOpenPage,
  downloadButton,
  onAddPage,
}: {
  binder: BinderDetail;
  onOpenPage: (ammId: string) => void;
  downloadButton: React.ReactNode;
  /** Ouvre l'ajout de page (prérempli depuis une page en trop). */
  onAddPage: (prefill?: { product_name: string; extra_id: string }) => void;
}) {
  const { t } = useTranslation();
  const { add, remove } = useExtraPages(binder.key);
  const canEdit = useCan('binder.edit');
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const pages = binder.sections.flatMap((section) => section.pages);
  const absent = pages.filter((p) => p.check?.result === 'ABSENT');
  const toScan = pages.filter((p) => p.to_scan);
  const toPrint = pages.filter((p) => p.to_print);
  const data = pages.filter((p) => p.conformity.criteria.some((c) => c.key === 'data' && c.ok === false));
  const groups = [
    { title: t('binders.leaves.groupAbsent'), items: absent },
    { title: t('binders.leaves.groupToScan'), items: toScan },
    { title: t('binders.leaves.groupToPrint'), items: toPrint },
    { title: t('binders.leaves.groupData'), items: data },
  ];
  return (
    <Box sx={paperSx}>
      <Holes />
      <FitToPage sx={{ pl: 7, pr: 4, py: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
          <Typography component="h2" sx={{ fontSize: 24, fontWeight: 900 }}>
            {t('binders.leaves.endTitle')}
          </Typography>
          {downloadButton}
        </Stack>
        <Typography sx={{ fontSize: 13, color: MUTED, mb: 2 }}>
          {t('binders.leaves.endStats', {
            checked: binder.checked,
            total: binder.total,
            conformes: binder.conformes,
            nonConformes: binder.non_conformes,
            corrected: binder.corrected,
            absent: binder.absent,
            toScan: binder.to_scan,
            toPrint: binder.to_print,
          })}
        </Typography>
        {groups.map((group) => (
          <Box key={group.title} sx={{ mb: 2 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 14 }}>
              {group.title} ({group.items.length})
            </Typography>
            {group.items.length === 0 ? (
              <Typography sx={{ fontSize: 13, color: MUTED }}>{t('binders.leaves.none')}</Typography>
            ) : (
              group.items.map((p) => (
                <Button
                  key={p.amm_id}
                  size="small"
                  onClick={() => onOpenPage(p.amm_id)}
                  sx={{ display: 'block', textAlign: 'left', color: INK, fontWeight: 500, py: 0 }}
                >
                  {t('binders.leaves.pageRef', { page: p.page, name: p.product_name })}
                </Button>
              ))
            )}
          </Box>
        ))}
        <Typography sx={{ fontWeight: 800, fontSize: 14 }}>
          {t('binders.leaves.extraPages', { n: binder.extra_pages.length })}
        </Typography>
        <Typography sx={{ fontSize: 12, color: MUTED, mb: 1 }}>{t('binders.leaves.extraHelp')}</Typography>
        {canEdit && (
          <Button size="small" variant="contained" onClick={() => onAddPage()} sx={{ mb: 1 }}>
            {t('binders.page.addPage')}
          </Button>
        )}
        {binder.extra_pages.map((extra) => (
          <Stack key={extra.id} direction="row" alignItems="center" gap={1}>
            <Typography sx={{ fontSize: 13, flex: 1 }}>
              {extra.product_name}
              {extra.note ? ` — ${extra.note}` : ''}{' '}
              <Box component="span" sx={{ color: MUTED, fontSize: 11 }}>
                ({extra.created_by ?? '—'}, {formatDateTime(extra.created_at)})
              </Box>
            </Typography>
            {canEdit && (
              <Button
                size="small"
                onClick={() => onAddPage({ product_name: extra.product_name, extra_id: extra.id })}
              >
                {t('binders.leaves.createPage')}
              </Button>
            )}
            {canEdit && (
              <Tooltip title={t('binders.leaves.remove')}>
                <IconButton
                  size="small"
                  onClick={() => remove.mutate(extra.id)}
                  aria-label={t('binders.leaves.removeNamed', { name: extra.product_name })}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Stack>
        ))}
        {canEdit && (
          <Stack
            component="form"
            direction={{ xs: 'column', sm: 'row' }}
            gap={1}
            sx={{ mt: 1 }}
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              add.mutate(
                { product_name: name, note },
                {
                  onSuccess: () => {
                    setName('');
                    setNote('');
                  },
                },
              );
            }}
          >
            <TextField
              size="small"
              label={t('binders.leaves.productRead')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              sx={{ bgcolor: '#fff', flex: 2 }}
            />
            <TextField
              size="small"
              label={t('binders.leaves.note')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              sx={{ bgcolor: '#fff', flex: 1 }}
            />
            <Button type="submit" variant="outlined" disabled={add.isPending || !name.trim()}>
              {t('binders.leaves.report')}
            </Button>
          </Stack>
        )}
        {add.isError && (
          <Typography sx={{ color: 'error.main', fontSize: 12, mt: 0.5 }}>
            {extractErrorMessage(add.error)}
          </Typography>
        )}
      </FitToPage>
    </Box>
  );
}

/** Verso d'une feuille déjà tournée (côté gauche du classeur ouvert). */
export function LeafBack({ label }: { label?: string }) {
  return (
    <Box sx={{ ...paperSx, bgcolor: '#f3efe6' }}>
      <Holes side="right" />
      {label && (
        <Typography
          sx={{
            position: 'absolute',
            bottom: 18,
            left: 24,
            right: 56,
            fontSize: 11,
            color: 'rgba(29,36,51,0.35)',
            fontWeight: 700,
            textTransform: 'uppercase',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          ← {label}
        </Typography>
      )}
    </Box>
  );
}

/** Contreplat intérieur du classeur (avant la première feuille). */
export function InsideCover() {
  return (
    <Box
      sx={{
        position: 'absolute',
        inset: 0,
        bgcolor: NAVY,
        backgroundImage:
          'repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0 1px, transparent 1px 6px)',
      }}
    />
  );
}
