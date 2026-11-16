import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Box, type SxProps, type Theme } from '@mui/material';

/** En dessous, le texte n'est plus lisible : on préfère alors laisser défiler la feuille. */
export const MIN_SCALE = 0.7;

/**
 * Plus grande échelle (entre `min` et 1) à laquelle le contenu tient dans `available`.
 *
 * Le contenu réduit est aussi élargi d'autant (il occupe toute la largeur de la feuille) : sa
 * hauteur dépend donc de l'échelle. `heightAt(s)` donne cette hauteur ; on cherche l'échelle par
 * dichotomie au lieu de la déduire d'une seule mesure. Jusqu'à la 1.3.2, une seule mesure
 * suffisait à changer l'échelle, qui changeait la hauteur, qui changeait l'échelle : sur beaucoup
 * de fenêtres (1366 × 768 par exemple) la feuille oscillait sans fin entre deux tailles.
 *
 * Renvoie `min` quand rien ne tient, même réduit au minimum.
 */
export function fitScale(heightAt: (scale: number) => number, available: number, min = MIN_SCALE): number {
  if (available <= 0 || heightAt(1) <= available) return 1;
  if (min * heightAt(min) > available) return min;
  let fits = min;
  let tooBig = 1;
  for (let step = 0; step < 7; step += 1) {
    const middle = (fits + tooBig) / 2;
    if (middle * heightAt(middle) <= available) fits = middle;
    else tooBig = middle;
  }
  // Arrondi vers le bas : deux mesures successives donnent la même échelle, et le contenu tient.
  return Math.floor(fits * 100) / 100;
}

/**
 * Contenu d'une feuille du classeur qui tient dans la feuille : quand il dépasse (petit écran,
 * page chargée), il est réduit juste assez pour être vu en entier. S'il ne tient pas même réduit
 * au minimum lisible, la feuille défile : rien n'est jamais coupé.
 */
export function FitToPage({ children, sx }: { children: ReactNode; sx?: SxProps<Theme> }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  // `height` : hauteur visible du contenu réduit, seulement quand la feuille défile.
  const [fit, setFit] = useState<{ scale: number; height: number | null }>({ scale: 1, height: null });

  useLayoutEffect(() => {
    const box = outer.current;
    const content = inner.current;
    if (!box || !content) return;
    const widthFor = (scale: number) => (scale < 1 ? `${100 / scale}%` : '100%');
    const measure = () => {
      const style = getComputedStyle(box);
      const available =
        box.clientHeight - parseFloat(style.paddingTop || '0') - parseFloat(style.paddingBottom || '0');
      if (available <= 0) return; // feuille pas encore affichée (page en train de tourner)
      // Hauteur naturelle à une échelle donnée (offsetHeight ignore la transformation).
      const heightAt = (scale: number) => {
        content.style.width = widthFor(scale);
        return content.offsetHeight;
      };
      const scale = fitScale(heightAt, available);
      const visible = Math.ceil(scale * heightAt(scale));
      const height = visible > available + 1 ? visible : null;
      // Les essais ont changé la largeur : on remet celle qui est affichée, React pose la suivante.
      content.style.width = widthFor(Number(content.dataset.fitScale) || 1);
      setFit((current) =>
        current.scale === scale && current.height === height ? current : { scale, height },
      );
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(box);
    observer?.observe(content);
    return () => observer?.disconnect();
  }, []);

  return (
    <Box
      ref={outer}
      sx={{
        position: 'absolute',
        inset: 0,
        overflowX: 'hidden',
        overflowY: fit.height === null ? 'hidden' : 'auto',
        ...(sx as object),
      }}
    >
      {/* Une transformation ne change pas la place prise : sans cette hauteur, le défilement
          irait jusqu'à la taille d'origine et laisserait du vide en bas. */}
      <div style={fit.height === null ? undefined : { height: fit.height, overflow: 'hidden' }}>
        <div
          ref={inner}
          data-fit-scale={fit.scale.toFixed(2)}
          style={{
            transform: fit.scale < 1 ? `scale(${fit.scale})` : undefined,
            transformOrigin: 'top left',
            width: fit.scale < 1 ? `${100 / fit.scale}%` : '100%',
          }}
        >
          {children}
        </div>
      </div>
    </Box>
  );
}
