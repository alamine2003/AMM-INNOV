/**
 * Bruit de page qui tourne, synthétisé (souffle de papier filtré) : pas de fichier audio à
 * charger. Désactivé par défaut, préférence gardée dans le navigateur.
 */
const SOUND_KEY = 'amm-gh.binders.sound';
let context: AudioContext | null = null;

export function readSound(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) === 'on';
  } catch {
    return false;
  }
}

export function saveSound(on: boolean) {
  try {
    localStorage.setItem(SOUND_KEY, on ? 'on' : 'off');
  } catch {
    // Stockage indisponible : la préférence vaut pour la session.
  }
}

export function playPageTurn(durationMs = 380) {
  try {
    const AudioCtor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtor) return;
    context ??= new AudioCtor();
    const ctx = context;
    const seconds = durationMs / 1000;
    const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      const t = i / data.length;
      // Froissement : bruit qui monte vite puis retombe, avec un léger claquement final.
      const envelope =
        Math.sin(Math.PI * Math.min(1, t * 1.6)) ** 2 * (1 - t) + (t > 0.86 ? 0.5 * (1 - t) : 0);
      data[i] = (Math.random() * 2 - 1) * envelope;
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(1800, ctx.currentTime);
    filter.frequency.linearRampToValueAtTime(4200, ctx.currentTime + seconds);
    filter.Q.value = 0.7;
    const gain = ctx.createGain();
    gain.gain.value = 0.18;
    source.connect(filter).connect(gain).connect(ctx.destination);
    source.start();
  } catch {
    // Son impossible (navigateur, politique d'autoplay) : on tourne la page en silence.
  }
}
