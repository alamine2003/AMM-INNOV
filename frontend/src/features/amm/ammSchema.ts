import { z } from 'zod';

export const ammSchema = z.object({
  product: z.string().min(1),
  country: z.string().min(1),
  original_number: z.string().nullable().optional(),
  original_start_date: z.string().nullable().optional(),
  original_end_date: z.string().nullable().optional(),
  dossier_state: z.enum(['COMPLET', 'INCOMPLET', 'INCONNU']),
  notes: z.string().optional(),
});
export type AmmFormValues = z.infer<typeof ammSchema>;
