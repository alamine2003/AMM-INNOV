import { extractErrorMessage } from '@/api/client';
import type { useDepositActions } from '@/api/hooks/useDeposits';
import { depositFiles } from '@/api/hooks/useDeposits';
import type { DepositPiece } from '@/api/types';
import { formatBytes, saveBlob } from '@/lib/download';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import CheckIcon from '@mui/icons-material/Check';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { Avatar, Box, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material';
import { useSnackbar } from 'notistack';
import { useRef, type ReactNode } from 'react';

/** Briques communes aux étapes d'un dossier de dépôt : cadre d'étape, envoi de fichier, pièce. */

export const PIECE_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.odt,.jpg,.jpeg,.png';
export const SCAN_ACCEPT = '.pdf,.jpg,.jpeg,.png';

export type Actions = ReturnType<typeof useDepositActions>;

export function useFail() {
  const { enqueueSnackbar } = useSnackbar();
  return (error: unknown) => enqueueSnackbar(extractErrorMessage(error), { variant: 'error' });
}

/** Une étape de la procédure : numéro, titre, état (fait, en cours, à venir). */
export function Section({
  index,
  title,
  subtitle,
  state,
  children,
  testId,
}: {
  index: number;
  title: string;
  subtitle?: ReactNode;
  state: 'done' | 'active' | 'todo';
  children?: ReactNode;
  testId?: string;
}) {
  const color = state === 'done' ? 'success.main' : state === 'active' ? 'primary.main' : 'grey.400';
  return (
    <Card
      variant="outlined"
      sx={{ mb: 2, borderLeft: 4, borderLeftColor: color, opacity: state === 'todo' ? 0.75 : 1 }}
      data-testid={testId}
    >
      <CardContent>
        <Stack direction="row" alignItems="center" gap={1.5} sx={{ mb: children ? 1.5 : 0 }}>
          <Avatar sx={{ bgcolor: color, width: 30, height: 30, fontSize: 15 }}>
            {state === 'done' ? <CheckIcon fontSize="small" /> : index}
          </Avatar>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="subtitle1" fontWeight={700} component="h2">
              {title}
            </Typography>
            {subtitle && (
              <Typography variant="body2" color="text.secondary" component="div">
                {subtitle}
              </Typography>
            )}
          </Box>
          {state === 'todo' && <LockOutlinedIcon fontSize="small" color="disabled" />}
        </Stack>
        {children}
      </CardContent>
    </Card>
  );
}

export function FileButton({
  label,
  accept,
  onFile,
  disabled,
  icon = <UploadFileIcon />,
  variant = 'outlined',
}: {
  label: string;
  accept: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  icon?: ReactNode;
  variant?: 'outlined' | 'text' | 'contained';
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        size="small"
        variant={variant}
        startIcon={icon}
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        {label}
      </Button>
      <input
        ref={input}
        type="file"
        hidden
        accept={accept}
        aria-label={label}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = '';
        }}
      />
    </>
  );
}

export function PieceChip({
  dossierId,
  piece,
  onDelete,
}: {
  dossierId: string;
  piece: DepositPiece;
  onDelete?: () => void;
}) {
  const fail = useFail();
  return (
    <Chip
      size="small"
      variant="outlined"
      icon={<AttachFileIcon />}
      label={`${piece.filename} · ${formatBytes(piece.size_bytes)}`}
      onClick={() =>
        depositFiles
          .piece(dossierId, piece.id)
          .then((blob) => saveBlob(blob, piece.filename))
          .catch(fail)
      }
      onDelete={onDelete}
      deleteIcon={onDelete ? <DeleteOutlineIcon aria-label={`Retirer ${piece.filename}`} /> : undefined}
      sx={{ maxWidth: '100%' }}
    />
  );
}
