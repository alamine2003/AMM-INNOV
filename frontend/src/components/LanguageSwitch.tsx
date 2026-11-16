import { ToggleButton, ToggleButtonGroup, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '@/features/auth/useLanguage';
import { LANGUAGES, type Language } from '@/lib/i18n';

/**
 * Bouton FR / EN. `onPrimary` : version claire, pour la barre du haut (fond bleu).
 * Chaque bouton porte le nom de sa langue dans cette langue : on le reconnaît sans lire l'autre.
 */
export function LanguageSwitch({ onPrimary = false, sx }: { onPrimary?: boolean; sx?: SxProps<Theme> }) {
  const { t } = useTranslation();
  const { language, choose } = useLanguage();
  const names: Record<Language, string> = { fr: t('app.languageFr'), en: t('app.languageEn') };
  const light = onPrimary
    ? {
        '& .MuiToggleButton-root': { color: 'rgba(255,255,255,0.85)', borderColor: 'rgba(255,255,255,0.5)' },
        '& .MuiToggleButton-root.Mui-selected': { color: 'primary.main', bgcolor: 'common.white' },
        '& .MuiToggleButton-root.Mui-selected:hover': { bgcolor: 'rgba(255,255,255,0.9)' },
      }
    : {};
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={language}
      onChange={(_event, next: Language | null) => next && choose(next)}
      aria-label={t('app.language')}
      data-testid="language-switch"
      sx={[
        { '& .MuiToggleButton-root': { py: 0.25, px: 1, fontWeight: 700, lineHeight: 1.6 } },
        light,
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {LANGUAGES.map((code) => (
        <ToggleButton
          key={code}
          value={code}
          aria-label={names[code]}
          lang={code}
          data-testid={`language-${code}`}
        >
          {code.toUpperCase()}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
