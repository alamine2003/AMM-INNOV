import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Box, type SxProps, type Theme } from '@mui/material';

/**
 * Contenu d'une feuille du classeur qui tient toujours dans la feuille, sans barre de défilement :
 * quand il dépasse (petit écran, page chargée), il est réduit juste assez pour être vu en entier.
 * « On voit tout ce qu'on veut voir sur la page » : rien n'est caché sous un défilement.
 */
export function FitToPage({ children, sx }: { children: ReactNode; sx?: SxProps<Theme> }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const box = outer.current;
    const content = inner.current;
    if (!box || !content) return;
    const measure = () => {
      const style = getComputedStyle(box);
      const available =
        box.clientHeight - parseFloat(style.paddingTop || '0') - parseFloat(style.paddingBottom || '0');
      // Hauteur naturelle : mesurée à l'échelle 1 (offsetHeight ignore la transformation).
      const needed = content.offsetHeight;
      const next = needed > available && available > 0 ? Math.max(0.55, available / needed) : 1;
      setScale((current) => (Math.abs(current - next) > 0.005 ? next : current));
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(box);
    observer?.observe(content);
    return () => observer?.disconnect();
  }, []);

  return (
    <Box ref={outer} sx={{ position: 'absolute', inset: 0, overflow: 'hidden', ...(sx as object) }}>
      <Box
        ref={inner}
        data-fit-scale={scale.toFixed(2)}
        sx={{
          transform: scale < 1 ? `scale(${scale})` : undefined,
          transformOrigin: 'top left',
          width: scale < 1 ? `${100 / scale}%` : '100%',
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
