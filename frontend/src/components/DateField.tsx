import type { ReactNode } from 'react';
import { useController, type Control, type FieldPath, type FieldValues } from 'react-hook-form';
import { DateInput, type DateInputProps } from './DateInput';

/**
 * Champ date d'un formulaire react-hook-form : sélecteur année → mois → jour (JJ/MM/AAAA).
 * Stocke null ou une date ISO.
 */
export function DateField<T extends FieldValues>({
  control,
  name,
  helperText,
  ...props
}: { control: Control<T>; name: FieldPath<T>; helperText?: ReactNode } & Omit<
  DateInputProps,
  'value' | 'onChange' | 'onBlur' | 'helperText'
>) {
  const { field, fieldState } = useController({ control, name });
  return (
    <DateInput
      {...props}
      value={(field.value as string | null | undefined) ?? null}
      onChange={field.onChange}
      onBlur={field.onBlur}
      error={!!fieldState.error || props.error}
      helperText={fieldState.error?.message ?? helperText}
    />
  );
}
