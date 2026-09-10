import { describe, expect, it } from 'vitest';
import { createFolderFormData, filesFromDrop, filesFromPicker, validateFolder } from '../folderUpload';

function fileAt(path: string, content = '%PDF-1.7 proof') {
  const file = new File([content], path.split('/').at(-1)!, { type: 'application/pdf' });
  Object.defineProperty(file, 'webkitRelativePath', { value: path });
  return file;
}

describe('upload de dossiers', () => {
  it('conserve les chemins imbriqués dans le même ordre que les fichiers multipart', () => {
    const files = filesFromPicker([
      fileAt('AMM Produit/RENOUVELLEMENT_2026/décision.pdf'),
      fileAt('AMM Produit/AMM_ORIGINE/décision.pdf'),
    ]);
    const form = createFolderFormData(files);
    expect(form.get('root_name')).toBe('AMM Produit');
    expect(JSON.parse(form.get('paths') as string)).toEqual([
      'AMM Produit/RENOUVELLEMENT_2026/décision.pdf',
      'AMM Produit/AMM_ORIGINE/décision.pdf',
    ]);
    expect(form.getAll('files')).toEqual(files.map(({ file }) => file));
  });

  it('rejette les chemins dangereux, les formats inattendus et les chemins répétés', () => {
    expect(() => createFolderFormData([{ file: fileAt('a.pdf'), path: '../a.pdf' }])).toThrow('invalide');
    expect(validateFolder(filesFromPicker([fileAt('AMM/programme.exe')])).join()).toContain(
      'format non pris en charge',
    );
    expect(validateFolder(filesFromPicker([fileAt('AMM/a.pdf'), fileAt('AMM/a.pdf')])).join()).toContain(
      'plusieurs fois',
    );
    expect(validateFolder(filesFromPicker([fileAt('AMM/a.pdf'), fileAt('autre/a.pdf')])).join()).toContain(
      'dossier unique',
    );
  });

  it('applique les plafonds et ignore les fichiers de métadonnées macOS', () => {
    const file = fileAt('AMM/decision.pdf');
    Object.defineProperty(file, 'size', { value: 26 * 1024 ** 2 });
    expect(validateFolder(filesFromPicker([file])).join()).toContain('25 Mo');
    expect(
      validateFolder(Array.from({ length: 201 }, (_, index) => ({ file, path: `AMM/${index}.pdf` }))).join(),
    ).toContain('200 fichiers');
    expect(filesFromPicker([fileAt('AMM/.DS_Store'), fileAt('AMM/decision.pdf')])).toHaveLength(1);
  });

  it('lit toutes les pages de sous-dossiers lors du glisser-déposer', async () => {
    const document = (name: string) => ({
      name,
      isFile: true,
      isDirectory: false,
      file: (callback: (file: File) => void) => callback(fileAt(name)),
    });
    const directory = (name: string, pages: unknown[][]) => ({
      name,
      isFile: false,
      isDirectory: true,
      createReader: () => {
        let page = 0;
        return { readEntries: (callback: (files: unknown[]) => void) => callback(pages[page++] ?? []) };
      },
    });
    const root = directory('AMM', [
      [directory('ORIGINE', [[document('a.pdf')], [document('b.pdf')]])],
      [document('c.pdf')],
    ]);
    const items = [{ webkitGetAsEntry: () => root }] as unknown as DataTransferItemList;
    expect((await filesFromDrop(items)).map(({ path }) => path)).toEqual([
      'AMM/ORIGINE/a.pdf',
      'AMM/ORIGINE/b.pdf',
      'AMM/c.pdf',
    ]);
  });
});
