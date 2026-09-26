import { Box, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';

/** Tracé vectoriel du logo Generic Healthcare (le « GH » et les deux flammes). */
const GH_BODY =
  'M241 830C215 827 196 808 170 759C140 704 130 671 121 601C111 529 131 438 170 367C198 316 215 301 242 299C279 297 624 296 634 298C647 301 654 307 658 318L659 323L659 379L659 435L658 440C654 449 647 454 636 458L631 459L494 460L356 460L351 462C334 467 328 475 317 505C303 549 304 586 321 630C329 650 336 658 350 662L355 663L396 663C460 663 474 661 479 653C484 643 476 637 455 635C439 633 430 627 424 615C420 606 420 602 420 558L420 518L422 514C425 505 432 499 443 496L448 494L574 494L700 494L705 493C716 489 722 484 725 473C726 470 726 458 726 394L727 319L729 314C737 297 741 296 822 296L883 296L888 297C902 301 909 309 911 324C911 329 912 399 911 565L911 799L910 805C907 817 900 825 890 828L884 830L824 831C761 831 755 831 746 828C738 825 732 818 728 807L727 802L726 731L726 660L724 655C716 629 676 625 665 648C660 657 660 656 660 730C659 792 659 802 658 806C654 821 646 828 630 830C622 831 249 831 241 830ZM357 125C354 124 345 123 337 123C299 119 292 114 254 53C234 22 232 17 240 9C246 1 251 0 302 0C370 0 370 0 408 57C416 69 424 82 426 85C436 102 434 115 422 120C413 124 374 127 357 125Z';
const GH_RED =
  'M31 362C11 361 2 356 1 344C0 333 2 328 28 290C38 273 52 253 58 243C64 234 72 222 76 216C80 210 86 201 89 196C107 166 122 154 145 150C156 148 225 148 232 150C250 154 254 164 245 184C239 195 211 239 194 264C190 271 182 283 177 291C148 339 131 356 110 360C96 363 56 364 31 362Z';
const GH_ORANGE =
  'M270 274C232 272 229 256 260 210C291 164 298 158 321 152C337 148 400 148 414 151C438 157 437 172 412 210C382 257 372 267 353 272C344 274 296 275 270 274Z';

export const LOGO_RED = '#E4211A';
export const LOGO_ORANGE = '#F27A03';

/**
 * Marque de l'application : « AMM » suivi du GH de Generic Healthcare, en un seul dessin
 * vectoriel. Le texte et le GH prennent la couleur courante (bleu GH sur fond clair, blanc sur
 * la bannière de connexion) ; les flammes gardent le rouge et l'orange du logo. Les filiales
 * pays travaillent sous la marque GH ; INNOV est le siège.
 */
export function BrandLogo({
  height = 28,
  sx,
}: {
  /** Hauteur en pixels ; la largeur suit. */
  height?: number;
  sx?: SxProps<Theme>;
}) {
  const { t } = useTranslation();
  return (
    <Box
      component="svg"
      viewBox="0 0 2812 831"
      role="img"
      aria-label={t('app.name')}
      sx={[
        { height, width: 'auto', display: 'block', flexShrink: 0, color: 'primary.main' },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <text
        x="0"
        y="830"
        fontSize="750"
        fontWeight="800"
        fontFamily='"Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
        textLength="1760"
        lengthAdjust="spacingAndGlyphs"
        fill="currentColor"
      >
        AMM
      </text>
      <g transform="translate(1900 0)">
        <path fill="currentColor" d={GH_BODY} />
        <path fill={LOGO_RED} d={GH_RED} />
        <path fill={LOGO_ORANGE} d={GH_ORANGE} />
      </g>
    </Box>
  );
}
