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
import { useDossierReport } from '@/api/hooks/useDossierImports';
import type { DossierReport, DossierReportItem } from '@/api/types';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { CappedList, plural } from './CappedList';

const PERIODS = [
  { days: 1, label: '24 h' },
  { days: 7, label: '7 jours' },
  { days: 30, label: '30 jours' },
];

type Kind = DossierReport['attention'][number]['kind'];

const KIND_LABELS: Record<Kind, string> = {
  question: 'AMM non identifiée',
  failed: 'Analyse échouée',
  ready: 'Non rangé',
  incomplete: 'Fiche à compléter',
};

type Detail = 'filed' | 'created' | 'corrections' | 'decisions';

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'vide';
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
  const [days, setDays] = useState(7);
  const report = useDossierReport(days);
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            Classement automatique
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={days}
            onChange={(_, value: number | null) => value && setDays(value)}
            aria-label="Période du récapitulatif"
          >
            {PERIODS.map((period) => (
              <ToggleButton key={period.days} value={period.days} sx={{ py: 0.25 }}>
                {period.label}
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
  const { totals } = report;
  const [detail, setDetail] = useState<Detail | null>(null);
  if (!totals.folders) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        Aucun dossier importé sur cette période.
      </Typography>
    );
  }
  const counters: { key: Detail; count: number; label: string }[] = [
    {
      key: 'filed',
      count: report.filed.length,
      label: plural(report.filed.length, 'dossier rangé', 'dossiers rangés'),
    },
    {
      key: 'created',
      count: report.created.length,
      label: plural(report.created.length, 'fiche créée', 'fiches créées'),
    },
    {
      key: 'corrections',
      count: report.corrections.length,
      label: plural(report.corrections.length, 'valeur corrigée', 'valeurs corrigées'),
    },
    {
      key: 'decisions',
      count: report.decisions.length,
      label: plural(report.decisions.length, 'décision automatique', 'décisions automatiques'),
    },
  ];
  const extra = [
    totals.documents && plural(totals.documents, 'document rangé', 'documents rangés'),
    totals.renewals && plural(totals.renewals, 'renouvellement ajouté', 'renouvellements ajoutés'),
    totals.completed && plural(totals.completed, 'champ complété', 'champs complétés'),
  ].filter(Boolean);
  return (
    <Stack spacing={1.5} sx={{ mt: 1.5 }}>
      {totals.in_progress > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary">
            {plural(totals.in_progress, 'dossier en analyse…', 'dossiers en analyse…')}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={Math.round(((totals.folders - totals.in_progress) / totals.folders) * 100)}
            aria-label="Avancement du classement"
          />
        </Box>
      )}

      <Attention items={report.attention} idle={totals.in_progress === 0} />

      <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" aria-label="Ce qui a été fait">
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
  const [kind, setKind] = useState<Kind | null>(null);
  if (!items.length) {
    return idle ? (
      <Alert severity="success" data-testid="report-attention" sx={{ py: 0 }}>
        Rien à traiter : tout a été rangé automatiquement.
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
        <Typography variant="subtitle2">À traiter par vous ({items.length})</Typography>
        {kinds.length > 1 &&
          kinds.map((value) => (
            <Chip
              key={value}
              size="small"
              clickable
              label={`${KIND_LABELS[value]} (${items.filter((item) => item.kind === value).length})`}
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
            <Who item={item} /> — {kinds.length > 1 ? '' : `${KIND_LABELS[item.kind]} : `}
            {item.reason}
          </>
        )}
      />
    </Alert>
  );
}

function DetailList({ report, detail }: { report: DossierReport; detail: Detail }) {
  if (detail === 'corrections') return <Corrections items={report.corrections} />;
  if (detail === 'created') {
    return (
      <CappedList
        items={report.created}
        itemKey={(item) => item.batch_id}
        render={(item) => (
          <>
            <Who item={item} />
            {item.number ? ` — n° ${item.number}` : ' — n° à compléter'}
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
            <Who item={item} /> : {item.message}
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
  const [all, setAll] = useState(false);
  return (
    <>
      <Table size="small" aria-label="Valeurs corrigées d’après les décisions officielles">
        <TableHead>
          <TableRow>
            <TableCell>AMM</TableCell>
            <TableCell>Champ</TableCell>
            <TableCell>Avant</TableCell>
            <TableCell>Après</TableCell>
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
          {all ? 'Réduire' : `Voir tout (${items.length})`}
        </Button>
      )}
    </>
  );
}
