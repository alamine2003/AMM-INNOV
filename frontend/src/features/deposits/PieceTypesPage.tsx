import { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import { Link } from 'react-router';
import { useCountries } from '@/api/hooks/useCatalog';
import { useDeletePieceType, usePieceTypes, useSavePieceType } from '@/api/hooks/useDeposits';
import type { PieceType } from '@/api/types';
import { Flag } from '@/features/binders/Flag';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { useFail } from './sections';

type Draft = Partial<PieceType> & { label: string };

function PieceDialog({ draft, onClose }: { draft: Draft | null; onClose: () => void }) {
  const save = useSavePieceType();
  const fail = useFail();
  const [value, setValue] = useState<Draft | null>(draft);
  if (!draft || !value) return null;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {value.id
          ? 'Modifier la pièce'
          : value.country
            ? `Pièce propre au pays (${value.country})`
            : 'Pièce de base'}
      </DialogTitle>
      <DialogContent>
        <Stack gap={2} sx={{ mt: 1 }}>
          <TextField
            autoFocus
            label="Pièce"
            value={value.label}
            onChange={(e) => setValue({ ...value, label: e.target.value })}
          />
          <TextField
            label="Précision (facultatif)"
            value={value.help_text ?? ''}
            onChange={(e) => setValue({ ...value, help_text: e.target.value })}
          />
          <Stack direction="row" gap={2} alignItems="center">
            <TextField
              type="number"
              label="Ordre"
              value={value.order ?? 100}
              onChange={(e) => setValue({ ...value, order: Number(e.target.value) })}
              sx={{ width: 120 }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={value.required ?? true}
                  onChange={(e) => setValue({ ...value, required: e.target.checked })}
                />
              }
              label="Obligatoire pour envoyer le dossier"
            />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Annuler</Button>
        <Button
          variant="contained"
          disabled={!value.label.trim() || save.isPending}
          onClick={() =>
            save.mutate(
              {
                id: value.id,
                label: value.label.trim(),
                help_text: value.help_text ?? '',
                order: value.order ?? 100,
                required: value.required ?? true,
                ...(value.id ? {} : { country: value.country ?? null }),
              },
              { onSuccess: onClose, onError: fail },
            )
          }
        >
          Enregistrer
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function PieceTypesPage() {
  const pieces = usePieceTypes();
  const countries = useCountries();
  const save = useSavePieceType();
  const remove = useDeletePieceType();
  const fail = useFail();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [country, setCountry] = useState('SN');

  if (pieces.isPending) return <LoadingBlock />;
  if (pieces.isError) return <ErrorBlock error={pieces.error} onRetry={() => pieces.refetch()} />;
  const active = pieces.data.filter((piece) => piece.active);
  const base = active.filter((piece) => !piece.country);
  const own = active.filter((piece) => piece.country === country);
  const countryName = (countries.data ?? []).find((c) => c.iso2 === country)?.name ?? country;

  const toggleExclusion = (piece: PieceType, asked: boolean) =>
    save.mutate(
      {
        id: piece.id,
        excluded_countries: asked
          ? piece.excluded_countries.filter((iso2) => iso2 !== country)
          : [...piece.excluded_countries, country],
      },
      { onError: fail },
    );

  const actions = (piece: PieceType) => (
    <>
      <Tooltip title="Modifier">
        <IconButton size="small" aria-label={`Modifier ${piece.label}`} onClick={() => setDraft(piece)}>
          <EditOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="Retirer (les dossiers déjà montés la gardent)">
        <IconButton
          size="small"
          aria-label={`Retirer ${piece.label}`}
          onClick={() => remove.mutate(piece.id, { onError: fail })}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </>
  );

  return (
    <Box>
      <Button component={Link} to="/depots" startIcon={<ArrowBackIcon />} size="small" sx={{ mb: 1 }}>
        Dépôts AMM
      </Button>
      <PageHeader
        title="Pièces demandées"
        subtitle="Liste de base du dossier de renouvellement, puis ajustements par pays. Un dossier ne part au pays que lorsque ses pièces obligatoires sont jointes."
      />
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardHeader
          title="Liste de base (tous les pays)"
          titleTypographyProps={{ variant: 'h6' }}
          action={
            <Button
              startIcon={<AddIcon />}
              onClick={() => setDraft({ label: '', required: true, order: 100 })}
            >
              Ajouter une pièce
            </Button>
          }
        />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Pièce</TableCell>
              <TableCell>Obligatoire</TableCell>
              <TableCell>Pays qui ne la demandent pas</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {base.map((piece) => (
              <TableRow key={piece.id}>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>
                    {piece.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {piece.help_text}
                  </Typography>
                </TableCell>
                <TableCell>{piece.required ? 'Oui' : 'Facultative'}</TableCell>
                <TableCell>
                  <Stack direction="row" gap={0.5} flexWrap="wrap">
                    {piece.excluded_countries.map((iso2) => (
                      <Chip key={iso2} size="small" label={iso2} />
                    ))}
                  </Stack>
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                  {actions(piece)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <Card variant="outlined">
        <CardHeader
          title="Ajustements par pays"
          subheader="Décochez une pièce de base que ce pays ne demande pas ; ajoutez les pièces propres au pays."
          titleTypographyProps={{ variant: 'h6' }}
          action={
            <TextField
              select
              size="small"
              label="Pays"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              sx={{ minWidth: 200 }}
            >
              {(countries.data ?? []).map((c) => (
                <MenuItem key={c.iso2} value={c.iso2}>
                  {c.name}
                </MenuItem>
              ))}
            </TextField>
          }
        />
        <CardContent sx={{ pt: 0 }}>
          <Stack direction="row" gap={1} alignItems="center" sx={{ mb: 1 }}>
            <Flag iso2={country} width={26} />
            <Typography variant="subtitle1" fontWeight={700}>
              Dossier de renouvellement — {countryName}
            </Typography>
          </Stack>
          <Stack>
            {base.map((piece) => {
              const asked = !piece.excluded_countries.includes(country);
              return (
                <FormControlLabel
                  key={piece.id}
                  control={
                    <Checkbox checked={asked} onChange={(e) => toggleExclusion(piece, e.target.checked)} />
                  }
                  label={
                    <Typography variant="body2" color={asked ? undefined : 'text.disabled'}>
                      {piece.label}
                      {!piece.required && ' (facultative)'}
                    </Typography>
                  }
                />
              );
            })}
            {own.map((piece) => (
              <Stack key={piece.id} direction="row" alignItems="center" gap={1} sx={{ pl: 1.5, py: 0.5 }}>
                <Chip size="small" color="primary" label={country} />
                <Typography variant="body2" sx={{ flexGrow: 1 }}>
                  {piece.label}
                  {!piece.required && ' (facultative)'}
                  {piece.help_text && (
                    <Typography component="span" variant="caption" color="text.secondary">
                      {' '}
                      — {piece.help_text}
                    </Typography>
                  )}
                </Typography>
                {actions(piece)}
              </Stack>
            ))}
          </Stack>
          <Button
            sx={{ mt: 1 }}
            startIcon={<AddIcon />}
            onClick={() => setDraft({ label: '', required: true, order: 200, country })}
          >
            Pièce propre à {countryName}
          </Button>
        </CardContent>
      </Card>
      <PieceDialog
        key={draft ? `${draft.id ?? 'new'}-${draft.country ?? ''}` : 'none'}
        draft={draft}
        onClose={() => setDraft(null)}
      />
    </Box>
  );
}
