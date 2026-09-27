import { Box, type SxProps, type Theme } from '@mui/material';
import { keyframes } from '@mui/material/styles';
import type { BinderResult } from '@/api/types';

export const INK = '#1d2433';
export const MUTED = '#6b7280';
export const LINE = '#d8d2c4';
export const NAVY = '#16213d';
export const PAPER = '#fbf8f1';

/** Feuille de papier : légère texture, ombre de pile. */
export const paperSx: SxProps<Theme> = {
  position: 'absolute',
  inset: 0,
  bgcolor: PAPER,
  backgroundImage:
    'radial-gradient(circle at 20% 10%, rgba(255,255,255,0.7), transparent 60%), ' +
    'linear-gradient(90deg, rgba(0,0,0,0.05), transparent 4%, transparent 96%, rgba(0,0,0,0.035))',
  color: INK,
  overflow: 'hidden',
};

/** Deux perforations renforcées, côté reliure. */
export function Holes({ side = 'left' }: { side?: 'left' | 'right' }) {
  return (
    <>
      {['32%', '68%'].map((top) => (
        <Box
          key={top}
          aria-hidden
          sx={{
            position: 'absolute',
            top,
            [side]: 14,
            width: 22,
            height: 22,
            mt: '-11px',
            borderRadius: '50%',
            bgcolor: '#8f887a',
            boxShadow: 'inset 1px 2px 3px rgba(0,0,0,0.55), 0 0 0 4px #efe9dc, 0 0 0 5.5px #cfc7b5',
          }}
        />
      ))}
    </>
  );
}

export const STAMPS: Record<BinderResult, { label: string; color: string }> = {
  CONFORME: { label: 'VÉRIFIÉ', color: '#2e7d32' },
  CORRIGE: { label: 'CORRIGÉ', color: '#e65100' },
  ABSENT: { label: 'ABSENT', color: '#c62828' },
};

const stampIn = keyframes`
  0% { transform: rotate(-12deg) scale(2.4); opacity: 0; }
  55% { transform: rotate(-12deg) scale(0.92); opacity: 1; }
  75% { transform: rotate(-12deg) scale(1.04); }
  100% { transform: rotate(-12deg) scale(1); opacity: 1; }
`;

/** Tampon encré ; `animate` le fait « tomber » sur la page juste après le constat. */
export function Stamp({
  result,
  caption,
  animate,
}: {
  result: BinderResult;
  caption: string;
  animate?: boolean;
}) {
  const { label, color } = STAMPS[result];
  return (
    <Box
      data-testid="binder-stamp"
      sx={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        px: 2.5,
        py: 0.75,
        border: `3px solid ${color}`,
        outline: `1px solid ${color}`,
        outlineOffset: '-7px',
        borderRadius: 1.5,
        color,
        bgcolor: `${color}0d`,
        transform: 'rotate(-12deg)',
        animation: animate ? `${stampIn} 420ms cubic-bezier(.2,.9,.3,1.2)` : 'none',
        mixBlendMode: 'multiply',
        userSelect: 'none',
      }}
    >
      <Box component="span" sx={{ fontWeight: 900, fontSize: 24, letterSpacing: 2, lineHeight: 1.2 }}>
        {label}
      </Box>
      <Box component="span" sx={{ fontWeight: 700, fontSize: 10 }}>
        {caption}
      </Box>
    </Box>
  );
}

export function Pill({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        px: 1.25,
        py: 0.25,
        borderRadius: 10,
        bgcolor: color,
        color: '#fff',
        fontSize: 12,
        fontWeight: 700,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </Box>
  );
}

/** Mélange une couleur hexadécimale avec du blanc (part de blanc entre 0 et 1). */
export function tint(hex: string, amount: number): string {
  const value = parseInt(hex.slice(1), 16);
  const mix = (channel: number) => Math.round(channel + (255 - channel) * amount);
  const r = mix((value >> 16) & 255);
  const g = mix((value >> 8) & 255);
  const b = mix(value & 255);
  return `rgb(${r}, ${g}, ${b})`;
}

export const STATUS_COLORS: Record<string, string> = {
  VALIDE: '#2e7d32',
  A_RENOUVELER: '#e65100',
  EXPIRE: '#c62828',
  INDETERMINE: MUTED,
};
