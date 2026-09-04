import { Box, Chip, Divider, IconButton, Stack, Tooltip, Typography } from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DownloadIcon from '@mui/icons-material/Download';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import DeleteIcon from '@mui/icons-material/Delete';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import { useTranslation } from 'react-i18next';
import type { AmmDocument, DocumentPeriod } from '@/api/types';
import { formatDate, formatDateTime } from '@/lib/dates';
import { formatBytes } from '@/lib/download';

export function DocumentTimeline({
  periods,
  onView,
  onDownload,
  onReplace,
  onDelete,
  canEdit,
  canDelete,
}: {
  periods: DocumentPeriod[];
  onView: (d: AmmDocument) => void;
  onDownload: (d: AmmDocument) => void;
  onReplace?: (d: AmmDocument) => void;
  onDelete?: (d: AmmDocument) => void;
  canEdit: boolean;
  canDelete: boolean;
}) {
  const { t } = useTranslation();
  // Le premier scan AMM du premier groupe non vide est le document en vigueur.
  const firstAmmDoc = periods.flatMap((p) => p.documents).find((d) => d.kind === 'AMM');

  return (
    <Box data-testid="document-timeline">
      {periods.map((period, idx) => (
        <Box
          key={`${period.period}-${period.sequence ?? 'orig'}`}
          sx={{ mb: 3 }}
          data-testid={`period-${period.period}-${period.sequence ?? 0}`}
        >
          <Divider textAlign="left" sx={{ mb: 1.5 }}>
            <Chip label={period.label} color={idx === 0 ? 'primary' : 'default'} size="small" />
          </Divider>
          {period.documents.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ pl: 4 }}>
              {t('documents.empty')}
            </Typography>
          )}
          <Stack
            spacing={1.5}
            sx={{
              position: 'relative',
              pl: 4,
              '&::before': {
                content: '""',
                position: 'absolute',
                left: 11,
                top: 0,
                bottom: 0,
                width: 2,
                bgcolor: 'divider',
              },
            }}
          >
            {period.documents.map((d) => {
              const isCurrent = firstAmmDoc?.id === d.id;
              return (
                <Box key={d.id} sx={{ position: 'relative' }} data-testid={`document-${d.id}`}>
                  <Box
                    sx={{
                      position: 'absolute',
                      left: -29,
                      top: 12,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      bgcolor: isCurrent ? 'success.main' : 'primary.main',
                      border: '2px solid #fff',
                    }}
                  />
                  <Box
                    sx={{
                      display: 'flex',
                      gap: 1.5,
                      alignItems: 'flex-start',
                      p: 1.5,
                      border: 1,
                      borderColor: isCurrent ? 'success.main' : 'divider',
                      borderRadius: 1,
                      bgcolor: 'background.paper',
                    }}
                  >
                    <PictureAsPdfIcon color={isCurrent ? 'success' : 'action'} sx={{ mt: 0.5 }} />
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        <Typography variant="subtitle2" noWrap>
                          {d.title || t(`documentKind.${d.kind}`)}
                        </Typography>
                        <Chip size="small" label={t(`documentKind.${d.kind}`)} variant="outlined" />
                        {isCurrent && (
                          <Chip
                            size="small"
                            color="success"
                            label={t('documents.current')}
                            data-testid="badge-current"
                          />
                        )}
                        {d.version > 1 && (
                          <Chip
                            size="small"
                            label={t('documents.version', { n: d.version })}
                            variant="outlined"
                          />
                        )}
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {t('documents.date')} : <strong>{formatDate(d.document_date)}</strong> ·{' '}
                        {formatBytes(d.size_bytes)}
                        {d.page_count ? ` · ${t('documents.pages', { count: d.page_count })}` : ''}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('documents.uploadedBy', {
                          email: d.uploaded_by_email,
                          date: formatDateTime(d.uploaded_at),
                        })}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={0}>
                      <Tooltip title={t('documents.view')}>
                        <IconButton size="small" onClick={() => onView(d)} aria-label={t('documents.view')}>
                          <VisibilityIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title={t('app.download')}>
                        <IconButton size="small" onClick={() => onDownload(d)} aria-label={t('app.download')}>
                          <DownloadIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {canEdit && onReplace && (
                        <Tooltip title={t('documents.replace')}>
                          <IconButton
                            size="small"
                            onClick={() => onReplace(d)}
                            aria-label={t('documents.replace')}
                          >
                            <SwapHorizIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                      {canDelete && onDelete && (
                        <Tooltip title={t('app.delete')}>
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => onDelete(d)}
                            aria-label={t('app.delete')}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </Stack>
                  </Box>
                </Box>
              );
            })}
          </Stack>
        </Box>
      ))}
    </Box>
  );
}
