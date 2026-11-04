import type { BinderDetail, BinderPage } from '@/api/types';

/** Une feuille du classeur : page de garde, intercalaire, page d'AMM ou bilan. */
export type Leaf =
  | { kind: 'title'; key: 'title' }
  | { kind: 'divider'; key: string; code: string }
  | { kind: 'page'; key: string; ammId: string; code: string }
  | { kind: 'end'; key: 'end' };

export type LeafFilter = 'all' | 'unchecked' | 'issues' | 'non_conformes';

export const FILTER_LABELS: Record<LeafFilter, string> = {
  all: 'Toutes les pages',
  unchecked: 'À vérifier ou revérifier',
  issues: 'Écarts et manques',
  non_conformes: 'Dossiers non conformes',
};

/**
 * Page qui mérite un œil attentif : écart avec le scan, décision en vigueur non scannée, n° ou
 * date de la décision en vigueur manquants (les mêmes règles que les 4 niveaux de vérification).
 */
export function hasIssue(page: BinderPage): boolean {
  const decision = page.renewal ?? page.original;
  const scan = page.conformity.criteria.find((c) => c.key === 'scan');
  return (
    page.discrepancies.length > 0 ||
    page.changed_since_check.length > 0 ||
    scan?.ok === false ||
    !decision.number ||
    !decision.start_date
  );
}

/** À (re)vérifier : jamais vérifiée, ou modifiée depuis par le dashboard ou un import. */
export function needsCheck(page: BinderPage): boolean {
  return !page.check || page.changed_since_check.length > 0;
}

function keep(page: BinderPage, filter: LeafFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'non_conformes') return page.conformity.status === 'NON_CONFORME';
  if (!needsCheck(page)) return false;
  return filter === 'unchecked' || hasIssue(page);
}

/**
 * Ordre des feuilles, figé au moment où le filtre est choisi : une page que l'on vient de
 * vérifier reste à sa place (on peut revenir dessus) au lieu de disparaître sous les doigts.
 */
export function buildLeaves(binder: BinderDetail, filter: LeafFilter): Leaf[] {
  const leaves: Leaf[] = [{ kind: 'title', key: 'title' }];
  for (const section of binder.sections) {
    leaves.push({ kind: 'divider', key: `divider:${section.code}`, code: section.code });
    for (const page of section.pages) {
      if (keep(page, filter)) {
        leaves.push({ kind: 'page', key: `page:${page.amm_id}`, ammId: page.amm_id, code: section.code });
      }
    }
  }
  leaves.push({ kind: 'end', key: 'end' });
  return leaves;
}

/** Première page pas encore vérifiée (reprise), sinon la page de garde. */
export function resumeIndex(leaves: Leaf[], binder: BinderDetail): number {
  const pages = pagesById(binder);
  const index = leaves.findIndex((leaf) => {
    const page = leaf.kind === 'page' ? pages.get(leaf.ammId) : undefined;
    return !!page && needsCheck(page);
  });
  return index >= 0 ? index : 0;
}

export function pagesById(binder: BinderDetail): Map<string, BinderPage> {
  const map = new Map<string, BinderPage>();
  for (const section of binder.sections) for (const page of section.pages) map.set(page.amm_id, page);
  return map;
}
