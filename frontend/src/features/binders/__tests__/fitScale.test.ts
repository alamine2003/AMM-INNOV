import { describe, expect, it } from 'vitest';
import { MIN_SCALE, fitScale } from '../FitToPage';

/**
 * Feuille de 400 px de large : réduite à l'échelle `s`, elle est mise en page sur 400 / s px.
 * `layout(width)` donne la hauteur du contenu pour cette largeur, comme le ferait le navigateur.
 */
const sheet = (layout: (width: number) => number) => (scale: number) => layout(400 / scale);

describe('échelle d’une feuille du classeur', () => {
  it('ne réduit rien quand le contenu tient', () => {
    expect(fitScale(() => 300, 480)).toBe(1);
    expect(fitScale(() => 480, 480)).toBe(1);
  });

  it('réduit juste assez, et le contenu réduit tient dans la feuille', () => {
    // Texte qui se replie : plus la mise en page est large, moins il est haut.
    const heightAt = sheet((width) => 200_000 / width);
    const scale = fitScale(heightAt, 420);
    expect(scale).toBeLessThan(1);
    expect(scale * heightAt(scale)).toBeLessThanOrEqual(420);
    // Juste assez : un cran au-dessus ne tiendrait plus.
    expect((scale + 0.02) * heightAt(scale + 0.02)).toBeGreaterThan(420);
  });

  it('donne la même échelle quand on remesure : la feuille ne oscille pas', () => {
    // Le cas de la production (fenêtre de 1366 × 768) : à l'échelle 1 le titre tient sur deux
    // lignes (500 px), un peu réduit il tient sur une seule (478 px). L'ancien calcul passait
    // de 0,96 à 1 puis de 1 à 0,96, sans fin.
    const heightAt = sheet((width) => (width >= 415 ? 478 : 500));
    const first = fitScale(heightAt, 480);
    const second = fitScale(heightAt, 480);
    expect(second).toBe(first);
    expect(first * heightAt(first)).toBeLessThanOrEqual(480);
  });

  it('tient compte d’un contenu qui change de forme (deux cartes côte à côte, puis empilées)', () => {
    const heightAt = sheet((width) => (width >= 540 ? 500 : 640));
    const scale = fitScale(heightAt, 420);
    expect(scale * heightAt(scale)).toBeLessThanOrEqual(420);
    expect(scale).toBeGreaterThanOrEqual(MIN_SCALE);
  });

  it('s’arrête au minimum lisible : au-delà, la feuille défile', () => {
    const heightAt = sheet(() => 2000);
    const scale = fitScale(heightAt, 400);
    expect(scale).toBe(MIN_SCALE);
    expect(scale * heightAt(scale)).toBeGreaterThan(400); // FitToPage active alors le défilement
  });

  it('ne fait rien tant que la feuille n’a pas de hauteur (page en train de tourner)', () => {
    expect(fitScale(() => 500, 0)).toBe(1);
  });
});
