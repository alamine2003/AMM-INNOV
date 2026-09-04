import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { useSnackbar } from 'notistack';
import { useReplaceDocument, useUploadDocument } from '@/api/hooks/useDocuments';
import type { Amm, AmmDocument, DocumentKind, Renewal } from '@/api/types';
import { DateField } from '@/components/DateField';
import { FileDropzone } from '@/components/FileDropzone';
import { extractErrorMessage } from '@/api/client';
import { sha256Hex } from '@/lib/download';

const MAX_BYTES = 25 * 1024 * 1024;
const ACCEPTED = ['application/pdf', 'image/jpeg', 'image/png'];
const KINDS: DocumentKind[] = ['AMM', 'RECEPISSE', 'COURRIER', 'AUTRE'];

const schema = z.object({
  kind: z.enum(['AMM', 'RECEPISSE', 'COURRIER', 'AUTRE']),
  document_date: z.string().nullable(),
  title: z.string().optional(),
  renewalId: z.string(),
});
type Values = z.infer<typeof schema>;

function UploadDocumentDialogInner({
  amm,
  renewals,
  existing,
  replaceTarget,
  open,
  onClose,
  defaultRenewalId,
}: {
  amm: Amm;
  renewals: Renewal[];
  existing: AmmDocument[];
  replaceTarget?: AmmDocument | null;
  open: boolean;
  onClose: () => void;
  defaultRenewalId?: string | null;
}) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const upload = useUploadDocument(amm.id);
  const replace = useReplaceDocument(amm.id);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const latestRenewal = renewals[0];
  const { control, register, handleSubmit, setValue, getValues } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      kind: replaceTarget?.kind ?? 'AMM',
      document_date:
        replaceTarget?.document_date ?? latestRenewal?.start_date ?? amm.original_start_date ?? null,
      title: replaceTarget?.title ?? '',
      renewalId: replaceTarget
        ? (replaceTarget.renewal ?? '')
        : (defaultRenewalId ?? latestRenewal?.id ?? ''),
    },
  });

  const renewalId = useWatch({ control, name: 'renewalId' });
  useEffect(() => {
    if (replaceTarget) return;
    const r = renewals.find((x) => x.id === renewalId);
    setValue('document_date', r?.start_date ?? r?.filing_date ?? amm.original_start_date ?? null);
  }, [renewalId, renewals, amm.original_start_date, setValue, replaceTarget]);

  const handleFile = async (f: File) => {
    setFileError(null);
    setDuplicate(false);
    if (!ACCEPTED.includes(f.type) || f.size > MAX_BYTES) {
      setFileError(t('documents.invalidFile'));
      setFile(null);
      return;
    }
    setFile(f);
    if (!getValues('title')) setValue('title', f.name.replace(/\.[^.]+$/, ''));
    const hash = await sha256Hex(f);
    if (hash && existing.some((d) => d.sha256 === hash)) setDuplicate(true);
  };

  const submit = (values: Values) => {
    if (!file) {
      setFileError(t('app.required'));
      return;
    }
    const common = {
      kind: values.kind,
      document_date: values.document_date ?? undefined,
      title: values.title || undefined,
      onProgress: setProgress,
    };
    const onSuccess = () => {
      enqueueSnackbar(t('documents.uploaded'), { variant: 'success' });
      onClose();
    };
    if (replaceTarget) replace.mutate({ documentId: replaceTarget.id, file, ...common }, { onSuccess });
    else upload.mutate({ file, renewalId: values.renewalId || null, ...common }, { onSuccess });
  };

  const pending = upload.isPending || replace.isPending;
  const error = upload.error ?? replace.error;

  return (
    <Dialog
      open={open}
      onClose={pending ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      data-testid="upload-dialog"
    >
      <DialogTitle>{replaceTarget ? t('documents.replace') : t('documents.upload')}</DialogTitle>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogContent>
          <Stack spacing={2}>
            <FileDropzone
              onFile={handleFile}
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              label={t('documents.dropzone')}
              hint={t('documents.dropzoneHint')}
              file={file}
              disabled={pending}
            />
            {fileError && <Alert severity="error">{fileError}</Alert>}
            {duplicate && <Alert severity="warning">{t('documents.duplicate')}</Alert>}
            {!replaceTarget && (
              <Controller
                control={control}
                name="renewalId"
                render={({ field }) => (
                  <TextField select label={t('documents.attachTo')} {...field}>
                    <MenuItem value="">{t('documents.attachOriginal')}</MenuItem>
                    {renewals.map((r) => (
                      <MenuItem key={r.id} value={r.id}>
                        {t('renewals.sequence', { n: r.sequence })} — {t(`workflow.${r.workflow_status}`)}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
            )}
            <Controller
              control={control}
              name="kind"
              render={({ field }) => (
                <TextField
                  select
                  label={t('documents.kind')}
                  {...field}
                  inputProps={{ 'data-testid': 'doc-kind' }}
                >
                  {KINDS.map((k) => (
                    <MenuItem key={k} value={k}>
                      {t(`documentKind.${k}`)}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <DateField control={control} name="document_date" label={t('documents.date')} />
            <TextField label={t('documents.titleField')} {...register('title')} />
            {progress !== null && pending && (
              <>
                <LinearProgress variant="determinate" value={progress} />
                <span>{t('documents.uploadProgress', { pct: progress })}</span>
              </>
            )}
            {error && <Alert severity="error">{extractErrorMessage(error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={pending}>
            {t('app.cancel')}
          </Button>
          <Button type="submit" variant="contained" disabled={pending || !file} data-testid="upload-submit">
            {t('documents.upload')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

type UploadDialogProps = Parameters<typeof UploadDocumentDialogInner>[0];

/** Le contenu est remonté à chaque ouverture (clé) : l'état du formulaire repart toujours de zéro. */
export function UploadDocumentDialog(props: UploadDialogProps) {
  if (!props.open) return null;
  return <UploadDocumentDialogInner key={props.replaceTarget?.id ?? 'new'} {...props} />;
}
