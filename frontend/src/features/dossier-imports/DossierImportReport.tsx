import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
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
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Link } from 'react-router';
import { useDossierReport } from '@/api/hooks/useDossierImports';
import type { DossierReport, DossierReportItem } from '@/api/types';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';

const PERIODS = [
  { days: 1, label: '24 h' },
  { days: 7, label: '7 jours' },
  { days: 30, label: '30 jours' },
];

const KIND_LABELS: Record<DossierReport['attention'][number]['kind'], string> = {
  question: 'AMM non identifiée',
  failed: 'Analyse échouée',
  ready: 'Non rangé',
  incomplete: 'Fiche à compléter',
};

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
  return item.amm_id ? (
    <MuiLink component={Link} to={`/amms/${item.amm_id}`}>
      {label}
    </MuiLink>
  ) : (
    <MuiLink component={Link} to={`/dossier-imports/${item.batch_id}`}>
      {label}
    </MuiLink>
  );
}

function Tile({ value, label }: { value: number; label: string }) {
  return (
    <Box sx={{ minWidth: 120, flex: '1 1 120px', p: 1.5, borderRadius: 2, bgcolor: 'background.default' }}>
      <Typography variant="h5" component="p" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  if (!count) return null;
  return (
    <Accordion disableGutters variant="outlined" sx={{ '&:before': { display: 'none' } }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle2">
          {title} ({count})
        </Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>{children}</AccordionDetails>
    </Accordion>
  );
}

/**
 * Récapitulatif du classement autonome : ce que l'application a rangé, corrigé, créé et décidé
 * seule, et uniquement les dossiers qui demandent une intervention.
 */
export function DossierImportReport() {
  const [days, setDays] = useState(7);
  const report = useDossierReport(days);
  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Typography variant="h6">Récapitulatif du classement automatique</Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={days}
            onChange={(_, value: number | null) => value && setDays(value)}
            aria-label="Période du récapitulatif"
          >
            {PERIODS.map((period) => (
              <ToggleButton key={period.days} value={period.days}>
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
  if (!totals.folders) {
    return (
      <Typography color="text.secondary" sx={{ mt: 2 }}>
        Aucun dossier importé sur cette période.
      </Typography>
    );
  }
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      {totals.in_progress > 0 && (
        <Box>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            Classement en cours : {totals.in_progress} dossier{totals.in_progress > 1 ? 's' : ''} en analyse…
          </Typography>
          <LinearProgress
            variant="determinate"
            value={Math.round(((totals.folders - totals.in_progress) / totals.folders) * 100)}
            aria-label="Avancement du classement"
          />
        </Box>
      )}
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Tile value={totals.filed} label="dossiers rangés" />
        <Tile value={totals.created} label="fiches créées" />
        <Tile value={totals.corrected} label="valeurs corrigées" />
        <Tile value={totals.completed} label="champs complétés" />
        <Tile value={totals.renewals} label="renouvellements ajoutés" />
        <Tile value={totals.documents} label="documents rangés" />
      </Stack>

      {report.attention.length ? (
        <Alert severity="warning" data-testid="report-attention">
          <Typography variant="subtitle2" gutterBottom>
            À traiter par vous ({report.attention.length})
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {report.attention.map((item, index) => (
              <li key={`${item.batch_id}-${index}`}>
                <strong>{KIND_LABELS[item.kind]}</strong> — <Who item={item} /> : {item.reason}
              </li>
            ))}
          </Box>
        </Alert>
      ) : (
        totals.in_progress === 0 && (
          <Alert severity="success" data-testid="report-attention">
            Rien à traiter : tout a été rangé automatiquement.
          </Alert>
        )
      )}

      <Box>
        <Section
          title="Valeurs corrigées d’après les décisions officielles"
          count={report.corrections.length}
        >
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>AMM</TableCell>
                <TableCell>Champ</TableCell>
                <TableCell>Avant</TableCell>
                <TableCell>Après</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {report.corrections.map((item, index) => (
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
        </Section>
        <Section title="Fiches créées" count={report.created.length}>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {report.created.map((item) => (
              <li key={item.batch_id}>
                <Who item={item} />
                {item.number ? ` — n° ${item.number}` : ' — n° à compléter'}
              </li>
            ))}
          </Box>
        </Section>
        <Section title="Décisions prises automatiquement" count={report.decisions.length}>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {report.decisions.map((item, index) => (
              <li key={`${item.batch_id}-${index}`}>
                <Who item={item} /> : {item.message}
              </li>
            ))}
          </Box>
        </Section>
        <Section title="Dossiers rangés" count={report.filed.length}>
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {report.filed.map((item) => (
              <li key={item.batch_id}>
                <Who item={item} />
                {item.lines.length ? ` — ${item.lines.slice(0, 3).join(' · ')}` : ''}
              </li>
            ))}
          </Box>
        </Section>
      </Box>
    </Stack>
  );
}
