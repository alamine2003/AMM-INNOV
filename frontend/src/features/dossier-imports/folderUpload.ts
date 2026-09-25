/** Ordered paths remain paired with their multipart files, including nested folders. */
export interface FolderFile {
  file: File;
  path: string;
}

export const FOLDER_LIMITS = {
  files: 200,
  fileBytes: 25 * 1024 ** 2,
  totalBytes: 250 * 1024 ** 2,
  // Un dossier pays ou gamme entier, découpé ensuite en un import par produit.
  dropFiles: 5000,
};

export function filesFromPicker(files: FileList | File[]): FolderFile[] {
  return Array.from(files, (file) => ({ file, path: file.webkitRelativePath || file.name })).filter(
    ({ file }) => !['.DS_Store', 'Thumbs.db'].includes(file.name),
  );
}

export function validateFolder(files: FolderFile[]): string[] {
  if (!files.length) return ['Le dossier ne contient aucun fichier.'];
  const errors: string[] = [];
  if (files.length > FOLDER_LIMITS.files) errors.push('Le dossier est limité à 200 fichiers.');
  if (files.reduce((total, { file }) => total + file.size, 0) > FOLDER_LIMITS.totalBytes)
    errors.push('La taille totale du dossier dépasse 250 Mo.');
  const paths = new Set<string>();
  const roots = new Set<string>();
  for (const { file, path } of files) {
    if (!/\.(pdf|jpe?g|png)$/i.test(file.name))
      errors.push(`${path} : format non pris en charge (PDF, JPEG ou PNG).`);
    if (!file.size) errors.push(`${path} : le fichier est vide.`);
    if (file.size > FOLDER_LIMITS.fileBytes) errors.push(`${path} : le fichier dépasse 25 Mo.`);
    if (
      path.length > 500 ||
      // eslint-disable-next-line no-control-regex -- caractères de contrôle interdits dans un chemin
      /[\\\u0000-\u001f]/.test(path) ||
      path.startsWith('/') ||
      path.split('/').some((part) => !part || part === '.' || part === '..')
    )
      errors.push(`${path} : chemin de fichier invalide.`);
    if (paths.has(path)) errors.push(`${path} : chemin présent plusieurs fois.`);
    paths.add(path);
    roots.add(path.split('/')[0]);
  }
  if (roots.size !== 1 || files.some(({ path }) => !path.includes('/')))
    errors.push('Sélectionnez un dossier unique contenant tous les documents et sous-dossiers.');
  if ([...roots].some((root) => root.length > 255)) errors.push('Le nom du dossier dépasse 255 caractères.');
  return errors;
}

/**
 * `reused` : empreinte SHA-256 des fichiers que le serveur possède déjà (même utilisateur). Ils
 * ne sont pas renvoyés : seuls leur chemin et leur empreinte partent, le serveur réutilise le
 * fichier stocké et sa lecture. Les décisions groupées d'un dossier pays ne partent qu'une fois.
 */
export function createFolderFormData(files: FolderFile[], reused: Map<string, string> = new Map()): FormData {
  const errors = validateFolder(files);
  if (errors.length) throw new Error(errors.join('\n'));
  const form = new FormData();
  const sent = files.filter(({ path }) => !reused.has(path));
  sent.forEach(({ file }) => form.append('files', file));
  form.append('paths', JSON.stringify(sent.map(({ path }) => path)));
  form.append(
    'reused',
    JSON.stringify(
      files.filter(({ path }) => reused.has(path)).map(({ path }) => ({ path, sha256: reused.get(path) })),
    ),
  );
  form.append('root_name', files[0].path.split('/')[0]);
  return form;
}

/** Empreinte SHA-256 (hexadécimal) d'un fichier ; null si le navigateur ne sait pas la calculer. */
export async function fileDigest(file: File): Promise<string | null> {
  try {
    const buffer = await new Response(file).arrayBuffer();
    const hash = await crypto.subtle.digest('SHA-256', buffer);
    return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
  } catch {
    return null;
  }
}

/** readEntries is paginated by browsers; read until the final empty batch. */
export async function filesFromDrop(items: DataTransferItemList): Promise<FolderFile[]> {
  if (!items.length || typeof items[0].webkitGetAsEntry !== 'function')
    throw new Error('Ce navigateur ne permet pas de déposer un dossier. Utilisez « Choisir un dossier ».');
  const entries = Array.from(items, (item) => item.webkitGetAsEntry()).filter(
    (entry): entry is FileSystemEntry => !!entry,
  );
  if (entries.length !== 1 || !entries[0].isDirectory)
    throw new Error('Déposez un dossier unique, ou utilisez « Choisir un dossier ».');
  const files: FolderFile[] = [];
  async function visit(entry: FileSystemEntry, parent = ''): Promise<void> {
    const path = `${parent}${entry.name}`;
    if (path.length > 500) throw new Error('Un chemin du dossier dépasse 500 caractères.');
    if (entry.isFile) {
      if (['.DS_Store', 'Thumbs.db'].includes(entry.name)) return;
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      );
      files.push({ file, path });
      if (files.length > FOLDER_LIMITS.dropFiles)
        throw new Error(`Le dossier dépasse ${FOLDER_LIMITS.dropFiles} fichiers : déposez-le pays par pays.`);
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let children: FileSystemEntry[];
      do {
        children = await new Promise<FileSystemEntry[]>((resolve, reject) =>
          reader.readEntries(resolve, reject),
        );
        for (const child of children) await visit(child, `${path}/`);
      } while (children.length);
    }
  }
  await visit(entries[0]);
  return files;
}

/** Sous-dossiers qui décrivent une période d'un même produit, pas un autre produit. */
const PERIOD_FOLDER = /^(amm[\s_-]*)?(origine|original|initial|renouv|renouvellement|renewal)/i;

export interface ProductGroup {
  name: string;
  files: FolderFile[];
}

/**
 * Fichiers mis de côté avant l'envoi : formats que l'import ne lit pas (tableurs, archives,
 * alias macOS…) ou trop volumineux. Ils ne bloquent plus le reste du dossier ; la liste est
 * affichée pour que le réglementaire sache ce qui n'a pas été envoyé.
 */
export function setAside(files: FolderFile[]): { kept: FolderFile[]; ignored: string[] } {
  const kept: FolderFile[] = [];
  const ignored: string[] = [];
  for (const entry of files) {
    if (!/\.(pdf|jpe?g|png)$/i.test(entry.file.name)) ignored.push(`${entry.path} (format non lu)`);
    else if (!entry.file.size) ignored.push(`${entry.path} (fichier vide)`);
    else if (entry.file.size > FOLDER_LIMITS.fileBytes) ignored.push(`${entry.path} (plus de 25 Mo)`);
    else kept.push(entry);
  }
  return { kept, ignored };
}

/**
 * Un dossier pays ou gamme (« CAMEROUN/OMEPRAL…/…pdf », « CARDIO/BENIN/BONCIPRO/BONCIPRO 500MG/…pdf »)
 * regroupe plusieurs produits : l'import intelligent traite une AMM à la fois, on crée donc un
 * import par dossier de présentation (le dossier qui contient les documents ; ses sous-dossiers
 * de période « ORIGINE », « RENOUVELLEMENT 2020 » restent avec lui). Les dossiers parents sont
 * gardés dans le nom (« CAMEROUN - OMEPRAL… ») pour que le pays reste reconnu par le chemin.
 * Un document posé au-dessus des dossiers produits (décision groupée à la racine du pays) est
 * commun : il est joint à chaque produit situé en dessous, et l'import y cherche la ligne du
 * produit. Renvoie [] si le dossier est un dossier produit.
 */
export function splitByProduct(files: FolderFile[]): ProductGroup[] {
  if (!files.length) return [];
  const root = files[0].path.split('/')[0];
  const productDirs = (parts: string[]) => {
    const dirs = parts.slice(1, -1);
    while (dirs.length && PERIOD_FOLDER.test(dirs[dirs.length - 1])) dirs.pop();
    return dirs;
  };
  const entries = [];
  for (const entry of files) {
    const parts = entry.path.split('/');
    if (parts[0] !== root) return [];
    entries.push({ entry, parts, dirs: productDirs(parts) });
  }
  const keys = new Set(entries.map(({ dirs }) => dirs.join('/')));
  const isParent = (key: string) =>
    [...keys].some((other) => other !== key && (key === '' || other.startsWith(`${key}/`)));
  const groups = new Map<string, { dirs: string[]; files: FolderFile[] }>();
  const common: typeof entries = [];
  for (const item of entries) {
    const key = item.dirs.join('/');
    if (!key || isParent(key)) {
      common.push(item);
      continue;
    }
    const group = groups.get(key) ?? { dirs: item.dirs, files: [] };
    group.files.push(item.entry);
    groups.set(key, group);
  }
  if (groups.size < 2) return [];
  return [...groups].map(([key, group]) => {
    const name = [root, ...group.dirs].join(' - ').slice(0, 255).trimEnd();
    const paths = new Set<string>();
    const list: FolderFile[] = [];
    const add = (file: File, path: string) => {
      if (paths.has(path)) return;
      paths.add(path);
      list.push({ file, path });
    };
    for (const file of group.files) {
      const parts = file.path.split('/');
      add(file.file, [name, ...parts.slice(1 + group.dirs.length)].join('/'));
    }
    for (const item of common) {
      const prefix = item.dirs.join('/');
      if (prefix && !key.startsWith(`${prefix}/`)) continue;
      add(item.entry.file, [name, 'Documents communs', item.parts[item.parts.length - 1]].join('/'));
    }
    return { name, files: list };
  });
}
