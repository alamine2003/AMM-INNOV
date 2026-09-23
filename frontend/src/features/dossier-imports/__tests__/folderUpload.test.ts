import { describe, expect, it } from 'vitest';
import {
  createFolderFormData,
  filesFromDrop,
  filesFromPicker,
  setAside,
  splitByProduct,
  validateFolder,
} from '../folderUpload';

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

  it('découpe un dossier pays en un import par produit, en gardant le pays dans la racine', () => {
    const groups = splitByProduct(
      filesFromPicker([
        fileAt('CAMEROUN/OMEPRAL 20MG GEL B28/AMM OMEPRAL.pdf'),
        fileAt('CAMEROUN/OMEPRAL 20MG GEL B28/OMEPRAL.pdf'),
        fileAt('CAMEROUN/FLUGEN 50MG :5ML PDRE SUSP BUV F60ML/AMM renouvellée FLUGEN SYROP.pdf'),
      ]),
    );
    expect(groups.map((g) => g.name)).toEqual([
      'CAMEROUN - OMEPRAL 20MG GEL B28',
      'CAMEROUN - FLUGEN 50MG :5ML PDRE SUSP BUV F60ML',
    ]);
    expect(groups[0].files.map((f) => f.path)).toEqual([
      'CAMEROUN - OMEPRAL 20MG GEL B28/AMM OMEPRAL.pdf',
      'CAMEROUN - OMEPRAL 20MG GEL B28/OMEPRAL.pdf',
    ]);
    expect(groups.every((g) => validateFolder(g.files).length === 0)).toBe(true);
  });

  it('ne découpe pas un dossier produit organisé par périodes', () => {
    expect(
      splitByProduct(
        filesFromPicker([
          fileAt('AMM Produit/AMM_ORIGINE/décision.pdf'),
          fileAt('AMM Produit/RENOUVELLEMENT_2026/décision.pdf'),
        ]),
      ),
    ).toEqual([]);
    expect(splitByProduct(filesFromPicker([fileAt('AMM Produit/décision.pdf')]))).toEqual([]);
  });

  it('découpe par présentation sous un dossier marque et joint les décisions groupées', () => {
    const groups = splitByProduct(
      filesFromPicker([
        fileAt('GUINEE/AMM Guinée 39 PRODUITS 2022.pdf'),
        fileAt('GUINEE/BONCIPRO/BONCIPRO 500MG CPR B20/AMM.pdf'),
        fileAt('GUINEE/BONCIPRO/BONCIPRO 750MG CPR B20/AMM.pdf'),
        fileAt('GUINEE/BONCIPRO/BONCIPRO 750MG CPR B20/RENOUVELLEMENT 2024/AMM.pdf'),
        fileAt('GUINEE/FLUGEN 100MG CPR B10/AMM FLUGEN.pdf'),
      ]),
    );
    expect(groups.map((g) => g.name)).toEqual([
      'GUINEE - BONCIPRO - BONCIPRO 500MG CPR B20',
      'GUINEE - BONCIPRO - BONCIPRO 750MG CPR B20',
      'GUINEE - FLUGEN 100MG CPR B10',
    ]);
    expect(groups[1].files.map((f) => f.path)).toEqual([
      'GUINEE - BONCIPRO - BONCIPRO 750MG CPR B20/AMM.pdf',
      'GUINEE - BONCIPRO - BONCIPRO 750MG CPR B20/RENOUVELLEMENT 2024/AMM.pdf',
      'GUINEE - BONCIPRO - BONCIPRO 750MG CPR B20/Documents communs/AMM Guinée 39 PRODUITS 2022.pdf',
    ]);
    expect(groups.every((g) => validateFolder(g.files).length === 0)).toBe(true);
  });

  it('découpe un dossier gamme (gamme / pays / produit)', () => {
    const groups = splitByProduct(
      filesFromPicker([
        fileAt('CARDIO AFRIQUE/BENIN/LOLIP 10MG CPR B30/LOLIP.pdf'),
        fileAt('CARDIO AFRIQUE/TOGO/LOLIP 10 MG CPR/AMM.pdf'),
      ]),
    );
    expect(groups.map((g) => g.name)).toEqual([
      'CARDIO AFRIQUE - BENIN - LOLIP 10MG CPR B30',
      'CARDIO AFRIQUE - TOGO - LOLIP 10 MG CPR',
    ]);
  });

  it('met de côté les formats non lus et les fichiers trop lourds sans bloquer le reste', () => {
    const big = fileAt('PAYS/B/scan.pdf');
    Object.defineProperty(big, 'size', { value: 26 * 1024 ** 2 });
    const { kept, ignored } = setAside(
      filesFromPicker([
        fileAt('PAYS/A/AMM.pdf'),
        fileAt('PAYS/A/liste.xls'),
        fileAt('PAYS/A/Archive.zip'),
        big,
      ]),
    );
    expect(kept.map((f) => f.path)).toEqual(['PAYS/A/AMM.pdf']);
    expect(ignored).toEqual([
      'PAYS/A/liste.xls (format non lu)',
      'PAYS/A/Archive.zip (format non lu)',
      'PAYS/B/scan.pdf (plus de 25 Mo)',
    ]);
  });
});
