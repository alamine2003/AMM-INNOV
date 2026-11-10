import type { BinderPage, BinderSlot } from '@/api/types';
import { DateInput, ValidityLine } from '@/components/DateInput';
import { addValidity } from '@/lib/dates';
import { Box, Button, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { LINE, MUTED } from './paper';
import { FIELDS, type Values, id, initialValues, show } from './sheetFields';

/** Bloc d'une page (AMM d'origine ou dernier renouvellement) : valeurs, constat, correction. */

export function SlotCard({
  page,
  slot,
  title,
  editing,
  values,
  onChange,
  years,
}: {
  page: BinderPage;
  slot: BinderSlot;
  title: string;
  years: number;
  editing: boolean;
  values: Values;
  onChange: (key: string, value: string) => void;
}) {
  const source = slot === 'original' ? page.original : page.renewal;
  const gaps = new Map(page.discrepancies.filter((d) => d.slot === slot).map((d) => [d.field, d]));
  const initial = initialValues(page);
  return (
    <Box
      sx={{
        flex: '1 1 220px',
        bgcolor: '#fff',
        border: `1px solid ${LINE}`,
        borderRadius: 2,
        p: 1.75,
        minWidth: 0,
      }}
    >
      <Typography sx={{ fontSize: 11, fontWeight: 800, color: MUTED, letterSpacing: 0.6, mb: 1 }}>
        {title.toUpperCase()}
      </Typography>
      {!source && !editing ? (
        <Typography sx={{ fontStyle: 'italic', color: MUTED, fontSize: 14 }}>
          Aucun renouvellement enregistré
        </Typography>
      ) : (
        FIELDS.map(({ field, label }) => {
          const key = id(slot, field);
          const gap = gaps.get(field);
          const changed = values[key] !== initial[key];
          return (
            <Box key={field} sx={{ py: 0.6, borderBottom: `1px dotted ${LINE}` }}>
              {editing ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  {field === 'number' ? (
                    <TextField
                      size="small"
                      label={label}
                      value={values[key]}
                      onChange={(e) => onChange(key, e.target.value)}
                      slotProps={{ inputLabel: { shrink: true } }}
                      sx={{
                        flex: 1,
                        '& .MuiOutlinedInput-root': { bgcolor: changed ? '#fff3b0' : '#fff' },
                      }}
                    />
                  ) : (
                    <DateInput
                      size="small"
                      label={label}
                      value={values[key]}
                      background={changed ? '#fff3b0' : '#fff'}
                      sx={{ flex: 1 }}
                      inputProps={{ 'data-testid': `sheet-${key}` }}
                      onChange={(value) => {
                        onChange(key, value ?? '');
                        // Date de début corrigée : la fin se recalcule sur la durée du pays.
                        if (field === 'start_date')
                          onChange(id(slot, 'end_date'), addValidity(value, years) ?? '');
                      }}
                    />
                  )}
                  {gap && (
                    <Tooltip describeChild title="Reprendre la valeur lue sur le scan">
                      <Button
                        size="small"
                        onClick={() => {
                          const scanValue = String(gap.scan ?? '');
                          onChange(key, scanValue);
                          if (field === 'start_date' && scanValue)
                            onChange(id(slot, 'end_date'), addValidity(scanValue, years) ?? '');
                        }}
                      >
                        Scan : {show(field, gap.scan)}
                      </Button>
                    </Tooltip>
                  )}
                </Stack>
              ) : (
                <Stack direction="row" alignItems="baseline" spacing={1}>
                  <Typography sx={{ fontSize: 12, color: MUTED, width: 96, flexShrink: 0 }}>
                    {label}
                  </Typography>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      component="span"
                      sx={{
                        fontWeight: 800,
                        fontSize: 15,
                        px: gap ? 0.5 : 0,
                        bgcolor: gap ? '#fff3b0' : 'transparent',
                        wordBreak: 'break-word',
                        whiteSpace: field === 'number' ? 'normal' : 'nowrap',
                      }}
                    >
                      {show(field, source?.[field])}
                    </Typography>
                    {gap && (
                      <Typography sx={{ fontSize: 11, color: '#b45309' }}>
                        le scan indique {show(field, gap.scan)}
                      </Typography>
                    )}
                  </Box>
                </Stack>
              )}
            </Box>
          );
        })
      )}
      {editing && (source || values[id(slot, 'start_date')]) && (
        <Box sx={{ mt: 1 }}>
          <ValidityLine
            start={values[id(slot, 'start_date')] || null}
            end={values[id(slot, 'end_date')] || null}
            years={years}
          />
        </Box>
      )}
    </Box>
  );
}

export const agedSx = {
  bgcolor: '#f1e4c3',
  backgroundImage:
    'radial-gradient(ellipse at 85% 90%, rgba(150,110,40,0.16), transparent 45%), ' +
    'radial-gradient(ellipse at 12% 18%, rgba(150,110,40,0.10), transparent 35%), ' +
    'linear-gradient(90deg, rgba(0,0,0,0.05), transparent 4%)',
};
