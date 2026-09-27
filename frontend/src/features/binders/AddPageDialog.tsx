import { useState } from 'react';
import {
  Alert,
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { extractErrorMessage } from '@/api/client';
import { useProductSearch } from '@/api/hooks/useCatalog';
import { useAddPage } from '@/api/hooks/useBinders';
import type { BinderAddPageResult, BinderDetail } from '@/api/types';
import { useDebouncedValue } from '@/lib/useDebouncedValue';

const RANGES = [
  { code: 'GENERALE', label: 'Générale' },
  { code: 'CARDIO', label: 'Cardio' },
  { code: 'BIEN_ETRE', label: 'Bien-être' },
];

/** Ajoute la page d'un produit oublié : l'AMM est créée dans le pays du classeur. */
export function AddPageDialog({
  binder,
  open,
  onClose,
  prefill,
  onAdded,
}: {
  binder: BinderDetail;
  open: boolean;
  onClose: () => void;
  prefill?: { product_name: string; extra_id: string } | null;
  onAdded: (result: BinderAddPageResult) => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      {open && (
        <AddPageForm
          key={prefill?.extra_id ?? 'new'}
          binder={binder}
          onClose={onClose}
          prefill={prefill}
          onAdded={onAdded}
        />
      )}
    </Dialog>
  );
}

function AddPageForm({
  binder,
  onClose,
  prefill,
  onAdded,
}: {
  binder: BinderDetail;
  onClose: () => void;
  prefill?: { product_name: string; extra_id: string } | null;
  onAdded: (result: BinderAddPageResult) => void;
}) {
  // Au siège, la gamme est celle du classeur ; ailleurs, on la choisit.
  const fixedRange = binder.key.includes('-');
  const [name, setName] = useState(prefill?.product_name ?? '');
  const [rangeCode, setRangeCode] = useState(binder.sections[0]?.code || 'GENERALE');
  const [number, setNumber] = useState('');
  const [start, setStart] = useState('');
  const search = useDebouncedValue(name, 250);
  const products = useProductSearch(search, search.length >= 2);
  const add = useAddPage(binder.key);

  const submit = () =>
    add.mutate(
      {
        product_name: name,
        range_code: fixedRange ? null : rangeCode,
        original_number: number,
        original_start_date: start || null,
        extra_id: prefill?.extra_id ?? null,
      },
      { onSuccess: onAdded },
    );

  return (
    <>
      <DialogTitle>Ajouter une page au classeur</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Un dossier est dans le classeur papier mais pas dans AMM GH : sa page est créée à sa place
          alphabétique, avec l'AMM du produit pour {binder.country_name}. Le scan pourra être importé ensuite,
          directement depuis la page.
        </Typography>
        <Stack spacing={2}>
          <Autocomplete
            freeSolo
            options={(products.data ?? []).map((p) => p.name)}
            inputValue={name}
            onInputChange={(_, value) => setName(value)}
            renderInput={(params) => (
              <TextField
                {...params}
                autoFocus
                required
                label="Produit (tel qu'écrit sur le dossier)"
                helperText="Choisissez un produit du catalogue s'il existe déjà, sinon il sera créé."
              />
            )}
          />
          {!fixedRange && (
            <TextField select label="Gamme" value={rangeCode} onChange={(e) => setRangeCode(e.target.value)}>
              {RANGES.map((range) => (
                <MenuItem key={range.code} value={range.code}>
                  {range.label}
                </MenuItem>
              ))}
            </TextField>
          )}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="N° d'AMM d'origine"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              sx={{ flex: 1 }}
            />
            <TextField
              label="Date de début"
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={{ flex: 1 }}
            />
          </Stack>
          {add.isError && <Alert severity="error">{extractErrorMessage(add.error)}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Annuler</Button>
        <Button variant="contained" onClick={submit} disabled={!name.trim() || add.isPending}>
          Ajouter la page
        </Button>
      </DialogActions>
    </>
  );
}
