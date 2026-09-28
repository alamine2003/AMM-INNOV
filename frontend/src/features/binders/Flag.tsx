import { Box } from '@mui/material';

/**
 * Drapeaux dessinés (SVG 3:2) des pays suivis : les émojis-drapeaux ne s'affichent pas sous
 * Windows. Dessins simplifiés, reconnaissables en petit format.
 */
const STAR =
  'M0,-1 L0.2245,-0.309 L0.951,-0.309 L0.363,0.118 L0.588,0.809 L0,0.382 L-0.588,0.809 L-0.363,0.118 L-0.951,-0.309 L-0.2245,-0.309 Z';

function star(cx: number, cy: number, r: number, fill: string) {
  return <path d={STAR} fill={fill} transform={`translate(${cx} ${cy}) scale(${r})`} />;
}

function vertical(colors: string[]) {
  const w = 30 / colors.length;
  return colors.map((color, i) => <rect key={i} x={i * w} y={0} width={w + 0.2} height={20} fill={color} />);
}

function horizontal(colors: string[]) {
  const h = 20 / colors.length;
  return colors.map((color, i) => <rect key={i} x={0} y={i * h} width={30} height={h + 0.2} fill={color} />);
}

const FLAGS: Record<string, React.ReactNode> = {
  SN: (
    <>
      {vertical(['#00853f', '#fdef42', '#e31b23'])}
      {star(15, 10, 3.2, '#00853f')}
    </>
  ),
  ML: <>{vertical(['#14b53a', '#fcd116', '#ce1126'])}</>,
  GN: <>{vertical(['#ce1126', '#fcd116', '#009460'])}</>,
  CI: <>{vertical(['#f77f00', '#ffffff', '#009e60'])}</>,
  TD: <>{vertical(['#002664', '#fecb00', '#c60c30'])}</>,
  CM: (
    <>
      {vertical(['#007a5e', '#ce1126', '#fcd116'])}
      {star(15, 10, 3, '#fcd116')}
    </>
  ),
  BF: (
    <>
      {horizontal(['#ef2b2d', '#009e49'])}
      {star(15, 10, 3.2, '#fcd116')}
    </>
  ),
  GA: <>{horizontal(['#009e60', '#fcd116', '#3a75c4'])}</>,
  NE: (
    <>
      {horizontal(['#e05206', '#ffffff', '#0db02b'])}
      <circle cx={15} cy={10} r={2.3} fill="#e05206" />
    </>
  ),
  GM: (
    <>
      <rect x={0} y={0} width={30} height={6} fill="#ce1126" />
      <rect x={0} y={6} width={30} height={1} fill="#ffffff" />
      <rect x={0} y={7} width={30} height={6} fill="#0c1c8c" />
      <rect x={0} y={13} width={30} height={1} fill="#ffffff" />
      <rect x={0} y={14} width={30} height={6} fill="#3a7728" />
    </>
  ),
  BJ: (
    <>
      <rect x={0} y={0} width={30} height={10} fill="#fcd116" />
      <rect x={0} y={10} width={30} height={10} fill="#e8112d" />
      <rect x={0} y={0} width={12} height={20} fill="#008751" />
    </>
  ),
  MG: (
    <>
      <rect x={0} y={0} width={30} height={10} fill="#fc3d32" />
      <rect x={0} y={10} width={30} height={10} fill="#007e3a" />
      <rect x={0} y={0} width={10} height={20} fill="#ffffff" />
    </>
  ),
  CG: (
    <>
      <rect x={0} y={0} width={30} height={20} fill="#fbde4a" />
      <path d="M0,0 L18,0 L0,20 Z" fill="#009543" />
      <path d="M30,0 L30,20 L12,20 Z" fill="#dc241f" />
    </>
  ),
  DJ: (
    <>
      {horizontal(['#6ab2e7', '#12ad2b'])}
      <path d="M0,0 L14,10 L0,20 Z" fill="#ffffff" />
      {star(4.5, 10, 2.2, '#d7141a')}
    </>
  ),
  TG: (
    <>
      {horizontal(['#006a4e', '#ffce00', '#006a4e', '#ffce00', '#006a4e'])}
      <rect x={0} y={0} width={12} height={12} fill="#d21034" />
      {star(6, 6, 3.2, '#ffffff')}
    </>
  ),
};

export function Flag({ iso2, width = 30 }: { iso2: string; width?: number }) {
  const flag = FLAGS[iso2];
  if (!flag) return null;
  return (
    <Box
      component="svg"
      viewBox="0 0 30 20"
      role="img"
      aria-label={`Drapeau ${iso2}`}
      sx={{
        width,
        height: (width * 2) / 3,
        display: 'block',
        borderRadius: '2px',
        boxShadow: '0 0 0 1px rgba(0,0,0,0.15)',
        flexShrink: 0,
      }}
    >
      {flag}
    </Box>
  );
}
