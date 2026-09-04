import { pdfjs } from 'react-pdf';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

/** Configure le worker pdf.js servi par Vite (import URL). */
export function configurePdfWorker() {
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
}
