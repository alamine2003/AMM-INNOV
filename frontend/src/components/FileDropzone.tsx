import { useRef, useState, type DragEvent } from 'react';
import { Box, Typography } from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';

export function FileDropzone({
  onFile,
  accept,
  label,
  hint,
  disabled,
  file,
}: {
  onFile: (file: File) => void;
  accept: string;
  label: string;
  hint?: string;
  disabled?: boolean;
  file?: File | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };

  return (
    <Box
      role="button"
      tabIndex={0}
      data-testid="dropzone"
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      sx={{
        border: '2px dashed',
        borderColor: dragging ? 'primary.main' : 'divider',
        bgcolor: dragging ? 'action.hover' : 'background.paper',
        borderRadius: 2,
        p: 3,
        textAlign: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        data-testid="dropzone-input"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = '';
        }}
      />
      <CloudUploadIcon color={dragging ? 'primary' : 'action'} sx={{ fontSize: 40 }} />
      <Typography variant="body2" sx={{ mt: 1 }}>
        {file ? file.name : label}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      )}
    </Box>
  );
}
