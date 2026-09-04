import { fetchBlob } from '@/api/client';

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export async function downloadFromApi(url: string, filename: string, params?: Record<string, unknown>) {
  const blob = await fetchBlob(url, params);
  saveBlob(blob, filename);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return '—';
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export async function sha256Hex(file: File): Promise<string | null> {
  try {
    if (!('crypto' in globalThis) || !globalThis.crypto?.subtle) return null;
    const buffer = await file.arrayBuffer();
    const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    return null;
  }
}
