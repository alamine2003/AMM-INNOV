import { Button, Chip, Tooltip } from '@mui/material';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useBinderLocation } from '@/api/hooks/useBinders';

/** Lien vers la page de l'AMM dans son classeur, avec l'état du constat de l'archiviste. */
export function BinderLink({ ammId }: { ammId: string | null | undefined }) {
  const { t } = useTranslation();
  const location = useBinderLocation(ammId);
  if (!ammId || !location.data) return null;
  const { binder_key, title, country_name, page, total, stale, conformity } = location.data;
  const failing = conformity.criteria.filter((c) => c.ok === false);
  const label = t('binders.link.label', { country: country_name, title, page, total });
  return (
    <Tooltip
      title={
        failing.length
          ? t('binders.link.failing', {
              label: conformity.label,
              list: failing.map((c) => `${c.label.toLowerCase()} (${c.detail})`).join(' ; '),
            })
          : t('binders.link.open', { label: conformity.label })
      }
    >
      <Button
        component={Link}
        to={`/classeurs/${binder_key}?amm=${ammId}`}
        variant="outlined"
        size="small"
        startIcon={<MenuBookIcon />}
        // L'emplacement d'icône agrandit son contenu : le tampon garde la taille d'une étiquette.
        sx={{ '& .MuiButton-endIcon > .MuiChip-root': { fontSize: 12, height: 22 } }}
        endIcon={
          stale ? (
            <Chip size="small" color="warning" label={t('binders.link.recheck')} />
          ) : conformity.status === 'CONFORME' ? (
            <Chip size="small" color="success" label={t('binders.link.conform')} />
          ) : conformity.status === 'NON_CONFORME' ? (
            <Chip size="small" color="error" label={t('binders.link.nonConform')} />
          ) : (
            <Chip size="small" variant="outlined" label={t('binders.link.toCheck')} />
          )
        }
      >
        {label}
      </Button>
    </Tooltip>
  );
}
