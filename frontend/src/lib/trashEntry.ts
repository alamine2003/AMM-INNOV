/** Entrée de corbeille renvoyée par une suppression (en-tête `X-Trash-Entry`), ou ''. */
export const trashEntryOf = (headers: unknown): string =>
  String((headers as Record<string, unknown> | undefined)?.['x-trash-entry'] ?? '');
