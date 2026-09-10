/** Ordered paths remain paired with their multipart files, including nested folders. */
export interface FolderFile {
  file: File;
  path: string;
}

export const FOLDER_LIMITS = { files: 200, fileBytes: 25 * 1024 ** 2, totalBytes: 250 * 1024 ** 2 };

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

export function createFolderFormData(files: FolderFile[]): FormData {
  const errors = validateFolder(files);
  if (errors.length) throw new Error(errors.join('\n'));
  const form = new FormData();
  files.forEach(({ file }) => form.append('files', file));
  form.append('paths', JSON.stringify(files.map(({ path }) => path)));
  form.append('root_name', files[0].path.split('/')[0]);
  return form;
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
      if (files.length > FOLDER_LIMITS.files) throw new Error('Le dossier est limité à 200 fichiers.');
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
