import type { BinderDetail, BinderPage } from '@/api/types';

/** Une feuille du classeur : page de garde, intercalaire, page d'AMM ou bilan. */
export type Leaf =
  | { kind: 'title'; key: 'title' }
  | { kind: 'divider'; key: string; code: string }
  | { kind: 'page'; key: string; ammId: string; code: string }
  | { kind: 'end'; key: 'end' };

export type LeafFilter = 'all' | 'unchecked' | 'issues';

export const FILTER_LABELS: Record<LeafFilter, string> = {
  all: 'Toutes les pages',
  unchecked: 'Pas encore vérifiées',
  issues: 'Écarts et manques',
};

/** Page qui mérite un œil attentif : écart avec le scan, pas de scan, n° ou date manquants. */
export function hasIssue(page: BinderPage): boolean {
  const original = page.original;
  return page.discrepancies.length > 0 || !page.scan || !original.number || !original.start_date;
}

function keep(page: BinderPage, filter: LeafFilter): boolean {
  if (filter === 'all') return true;
  if (page.check) return false;
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
  const index = leaves.findIndex((leaf) => leaf.kind === 'page' && !pages.get(leaf.ammId)?.check);
  return index >= 0 ? index : 0;
}

export function pagesById(binder: BinderDetail): Map<string, BinderPage> {
  const map = new Map<string, BinderPage>();
  for (const section of binder.sections) for (const page of section.pages) map.set(page.amm_id, page);
  return map;
}
