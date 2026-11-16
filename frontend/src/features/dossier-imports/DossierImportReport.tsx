import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useDossierReport } from '@/api/hooks/useDossierImports';
import type { DossierReport, DossierReportItem } from '@/api/types';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import i18n from '@/lib/i18n';
import { CappedList } from './CappedList';

// Clés de traduction : le libellé est résolu au rendu pour suivre la langue.
const PERIODS = [
  { days: 1, label: 'dossierImports.report.periods.d1' },
  { days: 7, label: 'dossierImports.report.periods.d7' },
  { days: 30, label: 'dossierImports.report.periods.d30' },
];

type Kind = DossierReport['attention'][number]['kind'];

const KIND_LABELS: Record<Kind, string> = {
  question: 'dossierImports.report.kinds.question',
  failed: 'dossierImports.report.kinds.failed',
  ready: 'dossierImports.report.kinds.ready',
  incomplete: 'dossierImports.report.kinds.incomplete',
};

type Detail = 'filed' | 'created' | 'corrections' | 'decisions';

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return i18n.t('dossierImports.values.empty');
  const text = String(value);
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  return iso ? `${iso[3]}/${iso[2]}/${iso[1]}` : text;
}

function Who({ item }: { item: DossierReportItem }) {
  const label = item.product
    ? `${item.product}${item.country_iso2 ? ` (${item.country_iso2})` : ''}`
    : item.folder;
  return (
    <MuiLink component={Link} to={item.amm_id ? `/amms/${item.amm_id}` : `/dossier-imports/${item.batch_id}`}>
      {label}
    </MuiLink>
  );
}

/**
 * Récapitulatif du classement autonome, en deux temps : d'abord ce qui attend l'utilisateur
 * (5 lignes au plus, filtrables), puis une ligne de chiffres dont chaque chiffre ouvre son détail.
 */
export function DossierImportReport() {
  const { t } = useTranslation();
  const [days, setDays] = useState(7);
  const report = useDossierReport(days);
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            {t('dossierImports.report.title')}
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={days}
            onChange={(_, value: number | null) => value && setDays(value)}
            aria-label={t('dossierImports.report.periodAria')}
          >
            {PERIODS.map((period) => (
              <ToggleButton key={period.days} value={period.days} sx={{ py: 0.25 }}>
                {t(period.label)}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Stack>
        {report.isPending ? (
          <LoadingBlock />
        ) : report.isError ? (
          <ErrorBlock error={report.error} onRetry={() => report.refetch()} />
        ) : (
          <ReportBody report={report.data} />
        )}
      </CardContent>
    </Card>
  );
}

function ReportBody({ report }: { report: DossierReport }) {
  const { t } = useTranslation();
  const { totals } = report;
  const [detail, setDetail] = useState<Detail | null>(null);
  if (!totals.folders) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {t('dossierImports.report.empty')}
      </Typography>
    );
  }
  const counters: { key: Detail; count: number; label: string }[] = [
    {
      key: 'filed',
      count: report.filed.length,
      label: t('dossierImports.report.counts.filed', { count: report.filed.length }),
    },
    {
      key: 'created',
      count: report.created.length,
      label: t('dossierImports.report.counts.created', { count: report.created.length }),
    },
    {
      key: 'corrections',
      count: report.corrections.length,
      label: t('dossierImports.report.counts.corrections', { count: report.corrections.length }),
    },
    {
      key: 'decisions',
      count: report.decisions.length,
      label: t('dossierImports.report.counts.decisions', { count: report.decisions.length }),
    },
  ];
  const extra = [
    totals.documents && t('dossierImports.report.counts.documents', { count: totals.documents }),
    totals.renewals && t('dossierImports.report.counts.renewals', { count: totals.renewals }),
    totals.completed && t('dossierImports.report.counts.completed', { count: totals.completed }),
  ].filter(Boolean);
  return (
    <Stack spacing={1.5} sx={{ mt: 1.5 }}>
      {totals.in_progress > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary">
            {t('dossierImports.report.counts.inProgress', { count: totals.in_progress })}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={Math.round(((totals.folders - totals.in_progress) / totals.folders) * 100)}
            aria-label={t('dossierImports.report.progressAria')}
          />
        </Box>
      )}

      <Attention items={report.attention} idle={totals.in_progress === 0} />

      <Stack
        direction="row"
        gap={1}
        flexWrap="wrap"
        alignItems="center"
        aria-label={t('dossierImports.report.doneAria')}
      >
        {counters
          .filter(({ count }) => count > 0)
          .map(({ key, label }) => (
            <Chip
              key={key}
              label={label}
              clickable
              color={detail === key ? 'primary' : 'default'}
              variant={detail === key ? 'filled' : 'outlined'}
              aria-pressed={detail === key}
              onClick={() => setDetail(detail === key ? null : key)}
            />
          ))}
        {extra.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            {extra.join(' · ')}
          </Typography>
        )}
      </Stack>

      {detail && (
        <Box sx={{ pl: 1, borderLeft: 3, borderColor: 'primary.light' }}>
          <DetailList report={report} detail={detail} />
        </Box>
      )}
    </Stack>
  );
}

/** Ce qui attend l'utilisateur : 5 lignes au plus, filtrables par motif. */
function Attention({ items, idle }: { items: DossierReport['attention']; idle: boolean }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<Kind | null>(null);
  if (!items.length) {
    return idle ? (
      <Alert severity="success" data-testid="report-attention" sx={{ py: 0 }}>
        {t('dossierImports.report.allFiled')}
      </Alert>
    ) : null;
  }
  const kinds = [...new Set(items.map((item) => item.kind))];
  const shown = kind ? items.filter((item) => item.kind === kind) : items;
  return (
    <Alert
      severity="warning"
      data-testid="report-attention"
      sx={{ '& .MuiAlert-message': { width: '100%' } }}
    >
      <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ mb: 0.5 }}>
        <Typography variant="subtitle2">
          {t('dossierImports.report.attentionTitle', { count: items.length })}
        </Typography>
        {kinds.length > 1 &&
          kinds.map((value) => (
            <Chip
              key={value}
              size="small"
              clickable
              label={`${t(KIND_LABELS[value])} (${items.filter((item) => item.kind === value).length})`}
              color={kind === value ? 'warning' : 'default'}
              variant={kind === value ? 'filled' : 'outlined'}
              onClick={() => setKind(kind === value ? null : value)}
            />
          ))}
      </Stack>
      <CappedList
        key={kind ?? 'all'}
        items={shown}
        itemKey={(item, index) => `${item.batch_id}-${index}`}
        render={(item) => (
          <>
            <Who item={item} /> —{' '}
            {kinds.length > 1
              ? ''
              : t('dossierImports.report.kindPrefix', { kind: t(KIND_LABELS[item.kind]) })}
            {item.reason}
          </>
        )}
      />
    </Alert>
  );
}

function DetailList({ report, detail }: { report: DossierReport; detail: Detail }) {
  const { t } = useTranslation();
  if (detail === 'corrections') return <Corrections items={report.corrections} />;
  if (detail === 'created') {
    return (
      <CappedList
        items={report.created}
        itemKey={(item) => item.batch_id}
        render={(item) => (
          <>
            <Who item={item} />
            {` — ${item.number ? t('dossierImports.report.numberLine', { number: item.number }) : t('dossierImports.report.numberToComplete')}`}
          </>
        )}
      />
    );
  }
  if (detail === 'decisions') {
    return (
      <CappedList
        items={report.decisions}
        itemKey={(item, index) => `${item.batch_id}-${index}`}
        render={(item) => (
          <>
            <Who item={item} />
            {t('dossierImports.report.decisionSeparator')}
            {item.message}
          </>
        )}
      />
    );
  }
  return (
    <CappedList
      items={report.filed}
      itemKey={(item) => item.batch_id}
      render={(item) => (
        <>
          <Who item={item} />
          {item.lines.length ? ` — ${item.lines.slice(0, 2).join(' · ')}` : ''}
        </>
      )}
    />
  );
}

function Corrections({ items }: { items: DossierReport['corrections'] }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  return (
    <>
      <Table size="small" aria-label={t('dossierImports.report.correctionsAria')}>
        <TableHead>
          <TableRow>
            <TableCell>{t('dossierImports.columns.ma')}</TableCell>
            <TableCell>{t('dossierImports.columns.field')}</TableCell>
            <TableCell>{t('dossierImports.columns.before')}</TableCell>
            <TableCell>{t('dossierImports.columns.after')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {(all ? items : items.slice(0, 5)).map((item, index) => (
            <TableRow key={`${item.batch_id}-${index}`}>
              <TableCell>
                <Who item={item} />
              </TableCell>
              <TableCell>{item.label}</TableCell>
              <TableCell sx={{ color: 'text.secondary', textDecoration: 'line-through' }}>
                {show(item.old)}
              </TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{show(item.new)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {items.length > 5 && (
        <Button size="small" sx={{ mt: 0.5 }} onClick={() => setAll(!all)}>
          {all
            ? t('dossierImports.cappedList.collapse')
            : t('dossierImports.cappedList.showAll', { count: items.length })}
        </Button>
      )}
    </>
  );
}
