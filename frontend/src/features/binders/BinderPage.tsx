import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  FormControlLabel,
  IconButton,
  LinearProgress,
  MenuItem,
  Slider,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { keyframes } from '@mui/material/styles';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { useSnackbar } from 'notistack';
import NoteAddIcon from '@mui/icons-material/NoteAdd';
import { useCurrentUser } from '@/api/hooks/useAuth';
import { useBinder, useBinderPresence } from '@/api/hooks/useBinders';
import type { BinderDetail, BinderPage as Page } from '@/api/types';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { AddPageDialog } from './AddPageDialog';
import { BinderDownload } from './BinderDownload';
import { BinderSheet } from './BinderSheet';
import { DividerLeaf, EndLeaf, InsideCover, LeafBack, TitleLeaf } from './BinderLeaves';
import { FILTER_LABELS, buildLeaves, pagesById, resumeIndex, type Leaf, type LeafFilter } from './leaves';
import { NAVY } from './paper';
import { playPageTurn, readSound, saveSound } from './sound';

const FLIP_MS = 380;
const ANIMATION_KEY = 'amm-gh.binders.animation';

const turnNext = keyframes`
  from { transform: rotateY(0deg); }
  to { transform: rotateY(-180deg); }
`;
const turnPrev = keyframes`
  from { transform: rotateY(-180deg); }
  to { transform: rotateY(0deg); }
`;
const lift = keyframes`
  0% { opacity: 0; }
  45% { opacity: 1; }
  100% { opacity: 0; }
`;
const fadeIn = keyframes`
  from { opacity: 0.4; }
  to { opacity: 1; }
`;

function readAnimation(): boolean {
  try {
    return localStorage.getItem(ANIMATION_KEY) !== 'off';
  } catch {
    return true;
  }
}

function saveAnimation(on: boolean) {
  try {
    localStorage.setItem(ANIMATION_KEY, on ? 'on' : 'off');
  } catch {
    // Stockage indisponible : la préférence vaut pour la session.
  }
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable;
}

interface Flip {
  dir: 'next' | 'prev';
  from: number;
}

interface Snapshot {
  key: string;
  filter: LeafFilter;
  leaves: Leaf[];
  source: BinderDetail;
  /** Pages du classeur (ordre) : un import ou le dashboard peut en ajouter ou en retirer. */
  signature: string;
}

function pageSignature(binder: BinderDetail): string {
  return binder.sections.map((s) => `${s.code}:${s.pages.map((p) => p.amm_id).join(',')}`).join('|');
}

/** Épaisseur de pile réaliste : 1 à 7 feuilles visibles selon le nombre de pages. */
function stackLayers(pagesInStack: number): number {
  return Math.max(1, Math.min(7, Math.ceil(pagesInStack / 18)));
}

function PageStack({ count, side }: { count: number; side: 'left' | 'right' }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => count - i).map((n) => (
        <Box
          key={n}
          aria-hidden
          sx={{
            position: 'absolute',
            inset: 0,
            transform: `translate(${side === 'right' ? n * 1.6 : -n * 1.6}px, ${n * 1.6}px)`,
            bgcolor: n % 2 ? '#efe9dc' : '#f7f2e8',
            borderRadius: 1,
            boxShadow: '0 1px 2px rgba(0,0,0,0.22)',
          }}
        />
      ))}
    </>
  );
}

export default function BinderPage() {
  const { binderKey } = useParams<{ binderKey: string }>();
  const query = useBinder(binderKey);
  if (query.isPending) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} onRetry={() => query.refetch()} />;
  return <OpenBinder binder={query.data} />;
}

function OpenBinder({ binder }: { binder: BinderDetail }) {
  const user = useCurrentUser();
  const isHq = user?.role === 'CEO_ADMIN' || user?.role === 'HQ_REGULATORY';
  const [filter, setFilter] = useState<LeafFilter>('all');
  const [animation, setAnimation] = useState(readAnimation);
  const [sound, setSound] = useState(readSound);
  useBinderPresence(binder.key);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [current, setCurrent] = useState(0);
  const [flip, setFlip] = useState<Flip | null>(null);
  const [jumped, setJumped] = useState(0);
  // Lien depuis la fiche AMM ou un import (`?amm=`) : le classeur s'ouvre sur sa page.
  const [searchParams] = useSearchParams();
  const [pending, setPending] = useState<string | null>(() => {
    const amm = searchParams.get('amm');
    return amm ? `page:${amm}` : null;
  });
  const [adding, setAdding] = useState<{ prefill?: { product_name: string; extra_id: string } } | null>(null);
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const bookRef = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);

  // L'ordre des feuilles est figé par filtre : une page vérifiée ne disparaît pas sous les doigts.
  // Une page attendue (ajoutée, ou masquée par le filtre) : on relit le classeur jusqu'à la trouver.
  const signature = pageSignature(binder);
  if (
    snapshot &&
    snapshot.key === binder.key &&
    snapshot.filter === filter &&
    !pending &&
    snapshot.signature !== signature
  ) {
    // Pages ajoutées ou retirées pendant la lecture (import Excel, import de dossier, dashboard) :
    // le classeur suit, en gardant la page ouverte et les pages déjà vues.
    const seen = new Set(snapshot.leaves.map((leaf) => leaf.key));
    const wanted = new Set(buildLeaves(binder, filter).map((leaf) => leaf.key));
    const leaves = buildLeaves(binder, 'all').filter((leaf) => seen.has(leaf.key) || wanted.has(leaf.key));
    const open = snapshot.leaves[Math.min(current, snapshot.leaves.length - 1)]?.key;
    const keep = leaves.findIndex((leaf) => leaf.key === open);
    setSnapshot({ key: binder.key, filter, leaves, source: binder, signature });
    setCurrent(keep >= 0 ? keep : Math.min(current, leaves.length - 1));
    setFlip(null);
  } else if (
    !snapshot ||
    snapshot.key !== binder.key ||
    snapshot.filter !== filter ||
    (pending && snapshot.source !== binder)
  ) {
    const leaves = buildLeaves(binder, filter);
    const target = pending ? leaves.findIndex((leaf) => leaf.key === pending) : -1;
    const fresh = !snapshot || snapshot.key !== binder.key || snapshot.filter !== filter;
    setSnapshot({ key: binder.key, filter, leaves, source: binder, signature });
    if (target >= 0) {
      setCurrent(target);
      setPending(null);
      setJumped((n) => n + 1);
    } else if (fresh) {
      setCurrent(resumeIndex(leaves, binder));
    }
    setFlip(null);
  }
  const leaves = snapshot?.leaves ?? buildLeaves(binder, filter);
  const pages = pagesById(binder);
  const last = leaves.length - 1;
  const index = Math.min(current, last);

  const go = useCallback(
    (target: number, animate = true) => {
      const next = Math.max(0, Math.min(target, leaves.length - 1));
      if (next === index) return;
      const step = Math.abs(next - index) === 1;
      if (sound) playPageTurn(animation && step ? FLIP_MS : 220);
      if (animation && animate && step) {
        setFlip({ dir: next > index ? 'next' : 'prev', from: index });
      } else {
        setFlip(null);
        setJumped((n) => n + 1);
      }
      setCurrent(next);
    },
    [animation, index, leaves.length, sound],
  );

  const indexRef = useRef(index);
  const goRef = useRef(go);
  useEffect(() => {
    indexRef.current = index;
    goRef.current = go;
  });

  useEffect(() => {
    if (!flip) return undefined;
    const timer = window.setTimeout(() => setFlip(null), FLIP_MS + 60);
    return () => window.clearTimeout(timer);
  }, [flip]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === 'ArrowRight') go(index + 1);
      else if (event.key === 'ArrowLeft') go(index - 1);
      else {
        const action = { c: 'conforme', e: 'corriger', a: 'absent' }[event.key.toLowerCase()];
        if (!action) return;
        const button = bookRef.current?.querySelector<HTMLButtonElement>(
          `[data-leaf="current"] [data-action="${action}"]`,
        );
        if (button && !button.disabled) {
          event.preventDefault();
          button.click();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, index]);

  const sectionOf = (code: string) => binder.sections.find((s) => s.code === code) ?? binder.sections[0];
  const total = binder.total;
  const leafIndex = (key: string) => leaves.findIndex((leaf) => leaf.key === key);
  const resume = resumeIndex(leaves, binder);
  const resumeLeaf = leaves[resume];
  const resumeLabel =
    resumeLeaf?.kind === 'page' ? (pages.get(resumeLeaf.ammId)?.product_name ?? null) : null;

  const renderLeaf = (at: number) => {
    const leaf = leaves[at];
    if (!leaf) return null;
    if (leaf.kind === 'title') {
      return (
        <TitleLeaf
          binder={binder}
          resumeLabel={resume > 0 ? resumeLabel : null}
          onResume={() => go(resume, false)}
        />
      );
    }
    if (leaf.kind === 'end') {
      return (
        <EndLeaf
          binder={binder}
          onOpenPage={(ammId) => {
            const target = leafIndex(`page:${ammId}`);
            if (target >= 0) go(target, false);
            else {
              // Page masquée par le filtre : on réaffiche tout le classeur, ouvert sur elle.
              setPending(`page:${ammId}`);
              setFilter('all');
            }
          }}
          onAddPage={(prefill) => setAdding({ prefill })}
          downloadButton={
            isHq ? (
              <BinderDownload binderKey={binder.key} label={`${binder.country_name} — ${binder.title}`} />
            ) : null
          }
        />
      );
    }
    const section = sectionOf(leaf.code);
    if (leaf.kind === 'divider') {
      return (
        <DividerLeaf
          section={section}
          pages={binder.sections.find((s) => s.code === leaf.code)?.pages ?? []}
        />
      );
    }
    const page: Page | undefined = pages.get(leaf.ammId);
    if (!page) return <LeafBack label="Page retirée du classeur" />;
    return (
      <BinderSheet
        key={page.amm_id}
        binder={binder}
        page={page}
        section={section}
        total={total}
        onChecked={() => {
          // Le tampon s'imprime, puis la page se tourne toute seule (si on n'a pas bougé).
          const from = at;
          window.setTimeout(
            () => {
              if (indexRef.current === from) goRef.current(from + 1);
            },
            animation ? 650 : 250,
          );
        }}
      />
    );
  };

  const leafLabel = (at: number) => {
    const leaf = leaves[at];
    if (!leaf) return '';
    if (leaf.kind === 'page') return pages.get(leaf.ammId)?.product_name ?? '';
    if (leaf.kind === 'divider') return `Intercalaire ${sectionOf(leaf.code).label}`;
    return leaf.kind === 'title' ? 'Page de garde' : 'Bilan';
  };

  // Sous la feuille qui tourne : la nouvelle page (en avant) ou l'ancienne (en arrière).
  const rightIndex = flip?.dir === 'prev' ? flip.from : index;
  const leftIndex = flip?.dir === 'next' ? flip.from - 1 : index - 1;
  const flipping = flip ? (flip.dir === 'next' ? flip.from : index) : null;
  const currentCode = (() => {
    const leaf = leaves[index];
    return leaf && (leaf.kind === 'page' || leaf.kind === 'divider') ? leaf.code : null;
  })();
  const progress = total ? (binder.checked / total) * 100 : 0;

  return (
    <Box>
      <Stack direction="row" alignItems="center" gap={1.5} flexWrap="wrap" sx={{ mb: 1.5 }}>
        <IconButton component={Link} to="/classeurs" aria-label="Retour à l'étagère">
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flex: '1 1 220px', minWidth: 0 }}>
          <Typography variant="h5" component="h1" noWrap>
            {binder.country_name} — {binder.title}
          </Typography>
          <Stack direction="row" alignItems="center" gap={1}>
            <LinearProgress
              variant="determinate"
              value={progress}
              color="success"
              sx={{ width: 160, height: 6, borderRadius: 3 }}
              aria-label="Avancement du classeur"
            />
            <Typography variant="body2" color="text.secondary">
              {binder.checked} / {total} vérifiées
            </Typography>
            {binder.stale > 0 && (
              <Chip
                size="small"
                color="warning"
                label={`${binder.stale} à revérifier`}
                onClick={() => setFilter('unchecked')}
              />
            )}
          </Stack>
        </Box>
        <TextField
          select
          size="small"
          label="Afficher"
          value={filter}
          onChange={(e) => setFilter(e.target.value as LeafFilter)}
          sx={{ minWidth: 190 }}
        >
          {(Object.keys(FILTER_LABELS) as LeafFilter[]).map((key) => (
            <MenuItem key={key} value={key}>
              {FILTER_LABELS[key]}
            </MenuItem>
          ))}
        </TextField>
        <FormControlLabel
          control={
            <Switch
              checked={animation}
              onChange={(e) => {
                setAnimation(e.target.checked);
                saveAnimation(e.target.checked);
              }}
            />
          }
          label="Animation"
        />
        <FormControlLabel
          control={
            <Switch
              checked={sound}
              onChange={(e) => {
                setSound(e.target.checked);
                saveSound(e.target.checked);
                if (e.target.checked) playPageTurn();
              }}
            />
          }
          label="Son"
        />
        <Button variant="outlined" startIcon={<NoteAddIcon />} onClick={() => setAdding({})}>
          Ajouter une page
        </Button>
        {isHq && <BinderDownload binderKey={binder.key} label={`${binder.country_name} — ${binder.title}`} />}
      </Stack>
      <AddPageDialog
        binder={binder}
        open={!!adding}
        prefill={adding?.prefill ?? null}
        onClose={() => setAdding(null)}
        onAdded={(result) => {
          setAdding(null);
          const target = `page:${result.amm_id}`;
          if (result.binder_key === binder.key) {
            // Le classeur est relu : on l'ouvre sur la nouvelle page, à sa place alphabétique.
            setPending(target);
            enqueueSnackbar('Page ajoutée : importez son scan directement depuis la page.', {
              variant: 'success',
            });
          } else {
            enqueueSnackbar(`Page rangée dans le classeur ${result.binder.title} (ordre alphabétique).`, {
              variant: 'info',
            });
            navigate(`/classeurs/${result.binder_key}`);
          }
        }}
      />

      <Box
        ref={bookRef}
        data-testid="binder-book"
        onPointerDown={(e) => {
          if ((e.target as HTMLElement).closest('button, input, textarea, a, [role="button"]')) return;
          pointer.current = { x: e.clientX, y: e.clientY };
        }}
        onPointerUp={(e) => {
          const start = pointer.current;
          pointer.current = null;
          if (!start) return;
          const dx = e.clientX - start.x;
          if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(e.clientY - start.y))
            go(dx < 0 ? index + 1 : index - 1);
        }}
        sx={{
          position: 'relative',
          mx: 'auto',
          maxWidth: 1240,
          height: { xs: 'calc(100vh - 230px)', md: 'calc(100vh - 210px)' },
          minHeight: 560,
          pr: { xs: 3.5, sm: 4.5 },
          touchAction: 'pan-y',
          userSelect: 'none',
        }}
      >
        {/* Le classeur ouvert : carton, mécanisme à levier, feuilles. */}
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            right: { xs: 28, sm: 36 },
            bgcolor: NAVY,
            borderRadius: 2.5,
            boxShadow: '0 18px 40px rgba(12,18,38,0.45), inset 0 0 0 3px rgba(255,255,255,0.05)',
            p: { xs: 1, sm: 1.75 },
            display: 'flex',
            perspective: '2400px',
          }}
        >
          <Box sx={{ position: 'relative', flex: 1, display: { xs: 'none', md: 'block' }, mr: 0.5 }}>
            {/* Feuilles déjà tournées : la pile s'épaissit à mesure qu'on avance. */}
            {leftIndex >= 0 && <PageStack count={stackLayers(index)} side="left" />}
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                borderRadius: 1,
                overflow: 'hidden',
                boxShadow: 'inset -14px 0 18px -12px rgba(0,0,0,0.5)',
              }}
            >
              {leftIndex >= 0 ? <LeafBack label={leafLabel(leftIndex)} /> : <InsideCover />}
            </Box>
          </Box>
          {/* Anneaux du mécanisme. */}
          <Box
            aria-hidden
            sx={{
              position: 'absolute',
              left: { xs: 6, md: '50%' },
              top: 0,
              bottom: 0,
              width: 0,
              zIndex: 3,
              display: { xs: 'none', md: 'block' },
            }}
          >
            {['32%', '68%'].map((top) => (
              <Box
                key={top}
                sx={{
                  position: 'absolute',
                  top,
                  left: -26,
                  width: 52,
                  height: 30,
                  mt: '-15px',
                  borderRadius: '50%',
                  border: '6px solid transparent',
                  borderTopColor: '#cfd5de',
                  borderLeftColor: '#9aa3b2',
                  borderRightColor: '#e8ecf2',
                  filter: 'drop-shadow(0 3px 3px rgba(0,0,0,0.45))',
                }}
              />
            ))}
          </Box>
          <Box sx={{ position: 'relative', flex: 1, ml: { md: 0.5 } }}>
            {/* Tranche des feuilles restantes : plus épaisse au début du classeur. */}
            {index < last && <PageStack count={stackLayers(last - index)} side="right" />}
            <Box
              data-leaf="current"
              key={`${rightIndex}-${jumped}`}
              sx={{
                position: 'absolute',
                inset: 0,
                borderRadius: 1,
                overflow: 'hidden',
                boxShadow: '0 2px 6px rgba(0,0,0,0.25)',
                animation: !flip && jumped ? `${fadeIn} 160ms ease-out` : 'none',
              }}
            >
              {renderLeaf(rightIndex)}
              {flip && (
                <Box
                  aria-hidden
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    background: 'linear-gradient(90deg, rgba(0,0,0,0.28), rgba(0,0,0,0.05) 60%, transparent)',
                    animation: `${lift} ${FLIP_MS}ms ease-in-out`,
                    opacity: 0,
                    pointerEvents: 'none',
                  }}
                />
              )}
            </Box>
            {/* Coin corné : tourner la page d'un clic. */}
            {index < last && !flip && (
              <Tooltip title="Page suivante">
                <Box
                  role="button"
                  aria-label="Page suivante (coin)"
                  onClick={() => go(index + 1)}
                  sx={{
                    position: 'absolute',
                    right: 0,
                    bottom: 0,
                    width: 34,
                    height: 34,
                    cursor: 'pointer',
                    zIndex: 2,
                    background: 'linear-gradient(135deg, transparent 50%, #e6dfcf 50%, #fff 75%)',
                    borderTopLeftRadius: 6,
                    boxShadow: '-2px -2px 4px rgba(0,0,0,0.12)',
                    transition: 'width 120ms, height 120ms',
                    '&:hover': { width: 48, height: 48 },
                  }}
                />
              </Tooltip>
            )}
            {flip && flipping !== null && (
              <Box
                aria-hidden
                sx={{
                  position: 'absolute',
                  inset: 0,
                  zIndex: 4,
                  transformOrigin: 'left center',
                  transformStyle: 'preserve-3d',
                  animation: `${flip.dir === 'next' ? turnNext : turnPrev} ${FLIP_MS}ms cubic-bezier(.45,.05,.35,1) forwards`,
                  pointerEvents: 'none',
                }}
              >
                <Box
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    backfaceVisibility: 'hidden',
                    borderRadius: 1,
                    overflow: 'hidden',
                    boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                  }}
                >
                  {renderLeaf(flipping)}
                </Box>
                <Box
                  sx={{
                    position: 'absolute',
                    inset: 0,
                    backfaceVisibility: 'hidden',
                    transform: 'rotateY(180deg)',
                    borderRadius: 1,
                    overflow: 'hidden',
                  }}
                >
                  <LeafBack label={leafLabel(flipping)} />
                </Box>
              </Box>
            )}
          </Box>
        </Box>

        {/* Onglets d'intercalaires sur la tranche. */}
        <Stack sx={{ position: 'absolute', right: 0, top: 36, gap: 1.25, zIndex: 5 }}>
          {binder.sections.map((section) => {
            const target = leafIndex(`divider:${section.code}`);
            const active = currentCode === section.code;
            return (
              <Tooltip
                key={section.code}
                title={`${section.label} — ${section.checked} / ${section.total}`}
                placement="left"
              >
                <Box
                  role="button"
                  aria-label={`Aller à l'intercalaire ${section.label}`}
                  onClick={() => go(target, false)}
                  sx={{
                    width: active ? { xs: 32, sm: 42 } : { xs: 26, sm: 34 },
                    height: 104,
                    bgcolor: section.color,
                    color: '#fff',
                    borderRadius: '0 8px 8px 0',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: active ? '3px 3px 8px rgba(0,0,0,0.35)' : '2px 2px 4px rgba(0,0,0,0.2)',
                    transition: 'width 150ms',
                    '&:hover': { width: { xs: 32, sm: 42 } },
                  }}
                >
                  <Box
                    component="span"
                    sx={{ writingMode: 'vertical-rl', fontWeight: 800, fontSize: 12, letterSpacing: 1 }}
                  >
                    {section.label.toUpperCase()}
                  </Box>
                </Box>
              </Tooltip>
            );
          })}
          <Box
            role="button"
            aria-label="Aller au bilan"
            onClick={() => go(last, false)}
            sx={{
              width: { xs: 26, sm: 34 },
              height: 70,
              bgcolor: '#6b7280',
              color: '#fff',
              borderRadius: '0 8px 8px 0',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Box component="span" sx={{ writingMode: 'vertical-rl', fontWeight: 800, fontSize: 11 }}>
              BILAN
            </Box>
          </Box>
        </Stack>
      </Box>

      <Stack direction="row" alignItems="center" gap={2} sx={{ maxWidth: 1240, mx: 'auto', mt: 1.5, px: 1 }}>
        <IconButton onClick={() => go(index - 1)} disabled={index === 0} aria-label="Page précédente">
          <NavigateBeforeIcon />
        </IconButton>
        <Slider
          size="small"
          value={index}
          min={0}
          max={Math.max(last, 1)}
          onChange={(_, value) => go(value as number, false)}
          valueLabelDisplay="auto"
          valueLabelFormat={(value) => leafLabel(value)}
          aria-label="Feuilleter le classeur"
          sx={{ flex: 1 }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 90, textAlign: 'right' }}>
          {index + 1} / {leaves.length}
        </Typography>
        <IconButton onClick={() => go(index + 1)} disabled={index === last} aria-label="Page suivante">
          <NavigateNextIcon />
        </IconButton>
      </Stack>
    </Box>
  );
}
