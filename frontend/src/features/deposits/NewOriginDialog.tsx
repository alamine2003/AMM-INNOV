import { useState } from 'react';
import {
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
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useCountries, useProductSearch } from '@/api/hooks/useCatalog';
import { useOpenDeposit } from '@/api/hooks/useDeposits';
import type { Product } from '@/api/types';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { useFail } from './sections';

/**
 * Siège : ouvrir le dossier de dépôt de la demande d'une AMM d'origine, pour un produit pas
 * encore enregistré dans le pays (1.4.1). La fiche AMM est créée sans n° ni dates.
 */
export function NewOriginDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fail = useFail();
  const countries = useCountries();
  const openDeposit = useOpenDeposit();
  const [search, setSearch] = useState('');
  const [product, setProduct] = useState<Product | null>(null);
  const [country, setCountry] = useState('');
  const [holder, setHolder] = useState('');
  const products = useProductSearch(useDebouncedValue(search, 250), open);
  const options = product
    ? [product, ...(products.data ?? []).filter((p) => p.id !== product.id)]
    : (products.data ?? []);

  const submit = () => {
    if (!product || !country) return;
    openDeposit.mutate(
      { product: product.id, country, holder: holder.trim() },
      {
        onSuccess: (dossier) => {
          onClose();
          navigate(`/depots/${dossier.id}`);
        },
        onError: fail,
      },
    );
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('deposits.origin.title')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('deposits.origin.text')}
        </Typography>
        <Stack spacing={2}>
          <Autocomplete
            options={options}
            getOptionLabel={(p) => p.name}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            filterOptions={(x) => x}
            loading={products.isFetching}
            value={product}
            inputValue={search}
            onInputChange={(_e, value) => setSearch(value)}
            onChange={(_e, value) => setProduct(value)}
            noOptionsText={t('deposits.origin.productHint')}
            renderInput={(params) => (
              <TextField
                {...params}
                label={t('deposits.origin.product')}
                helperText={t('deposits.origin.productHint')}
              />
            )}
          />
          <TextField
            select
            label={t('deposits.origin.country')}
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            data-testid="origin-country"
          >
            {(countries.data ?? []).map((c) => (
              <MenuItem key={c.iso2} value={c.iso2}>
                {c.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label={t('deposits.origin.holder')}
            value={holder}
            onChange={(e) => setHolder(e.target.value)}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('app.cancel')}</Button>
        <Button variant="contained" disabled={!product || !country || openDeposit.isPending} onClick={submit}>
          {t('deposits.origin.open')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
