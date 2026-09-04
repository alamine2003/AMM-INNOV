import { TextField, type TextFieldProps } from '@mui/material';
import { useController, type Control, type FieldPath, type FieldValues } from 'react-hook-form';

/**
 * Champ date natif (AAAA-MM-JJ côté valeur, affiché en JJ/MM/AAAA par le navigateur en locale fr).
 * Stocke '' ou une date ISO.
 */
export function DateField<T extends FieldValues>({
  control,
  name,
  ...props
}: { control: Control<T>; name: FieldPath<T> } & Omit<TextFieldProps, 'name' | 'value' | 'onChange'>) {
  const { field, fieldState } = useController({ control, name });
  return (
    <TextField
      {...props}
      type="date"
      value={(field.value as string | null | undefined) ?? ''}
      onChange={(e) => field.onChange(e.target.value || null)}
      onBlur={field.onBlur}
      inputRef={field.ref}
      error={!!fieldState.error || props.error}
      helperText={fieldState.error?.message ?? props.helperText}
      slotProps={{ inputLabel: { shrink: true }, ...props.slotProps }}
      fullWidth
    />
  );
}
