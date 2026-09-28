import { Button, Chip, Tooltip } from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { Link } from 'react-router';
import { useBinderLocation } from '@/api/hooks/useBinders';
import { STAMPS } from './paper';

/** Lien vers la page de l'AMM dans son classeur, avec l'état du constat de l'archiviste. */
export function BinderLink({ ammId }: { ammId: string | null | undefined }) {
  const location = useBinderLocation(ammId);
  if (!ammId || !location.data) return null;
  const { binder_key, title, country_name, page, total, check, stale } = location.data;
  const label = `Classeur ${country_name} — ${title} · page ${page}/${total}`;
  return (
    <Tooltip title="Ouvrir le classeur sur la page de cette AMM">
      <Button
        component={Link}
        to={`/classeurs/${binder_key}?amm=${ammId}`}
        variant="outlined"
        size="small"
        startIcon={<MenuBookIcon />}
        endIcon={
          stale ? (
            <Chip size="small" color="warning" label="À revérifier" />
          ) : check ? (
            <Chip
              size="small"
              label={STAMPS[check.result].label.toLowerCase()}
              sx={{ bgcolor: STAMPS[check.result].color, color: '#fff' }}
            />
          ) : (
            <Chip size="small" variant="outlined" label="à vérifier" />
          )
        }
      >
        {label}
      </Button>
    </Tooltip>
  );
}
