/**
 * Contrat API ↔ frontend, vérifié à la compilation.
 *
 * `schema.d.ts` est généré depuis le schéma OpenAPI du backend (`npm run api:types`, vérifié en
 * CI). Chaque ligne ci-dessous affirme qu'une réponse de l'API est assignable au type manuel
 * utilisé par les composants : si le backend renomme un champ ou change un enum, `tsc` échoue
 * ici au lieu de laisser planter une page en production (cause des dix anomalies du test
 * navigateur du 5 septembre 2026).
 *
 * Ce fichier n'exporte rien d'utile à l'exécution ; il est inclus dans `tsc -b`.
 */
import type { components } from './schema';
import type {
  Alert,
  AlertRule,
  Amm,
  AmmDocument,
  BinderAddPageResult,
  BinderCorrection,
  BinderPageScanResult,
  BinderDetail,
  BinderExport,
  BinderLocation,
  BinderResult,
  BinderSummary,
  DepositDetail,
  DepositSuggestion,
  DepositSummary,
  PieceType,
  Country,
  DossierReviewPoint,
  Health,
  HistoryEntry,
  ImportBatch,
  ImportRow,
  Notification,
  Product,
  ProductRange,
  Renewal,
  User,
} from './types';

type Schemas = components['schemas'];

/**
 * Un serializer DRF émet toujours tous ses champs dans une réponse ; le schéma OpenAPI ne les
 * marque pourtant « required » que sans valeur par défaut. `Complete` rétablit cette réalité
 * (les unions avec `null` sont conservées).
 */
type Complete<T> = { [K in keyof T]-?: T[K] };

/** `true` si toute réponse `From` (API) est acceptée là où le frontend attend `To`. */
type Assignable<From, To> = Complete<From> extends To ? true : false;
type Assert<T extends true> = T;

// --- Réponses de l'API → types utilisés par l'interface
export type _Alert = Assert<Assignable<Schemas['Alert'], Alert>>;
export type _AlertRule = Assert<Assignable<Schemas['AlertRule'], AlertRule>>;
export type _AmmList = Assert<Assignable<Schemas['AmmList'], Amm>>;
export type _AmmDetail = Assert<Assignable<Schemas['AmmDetail'], Amm>>;
export type _Renewal = Assert<Assignable<Schemas['Renewal'], Renewal>>;
export type _Document = Assert<Assignable<Schemas['Document'], AmmDocument>>;
export type _DocumentDetail = Assert<Assignable<Schemas['DocumentDetail'], AmmDocument>>;
export type _Health = Assert<Assignable<Schemas['Health'], Health>>;
export type _Notification = Assert<Assignable<Schemas['Notification'], Notification>>;
export type _Product = Assert<Assignable<Schemas['Product'], Product>>;
export type _ProductRange = Assert<Assignable<Schemas['ProductRange'], ProductRange>>;
export type _Country = Assert<Assignable<Schemas['Country'], Country>>;
export type _User = Assert<Assignable<Schemas['User'], User>>;
export type _ImportBatch = Assert<Assignable<Schemas['ImportBatch'], ImportBatch>>;
export type _ImportRow = Assert<Assignable<Schemas['ImportRow'], ImportRow>>;
export type _HistoryEntry = Assert<Assignable<Schemas['HistoryEntry'], HistoryEntry>>;
export type _DossierReviewPoint = Assert<Assignable<Schemas['DossierReviewPoint'], DossierReviewPoint>>;
export type _BinderSummary = Assert<Assignable<Schemas['BinderSummary'], BinderSummary>>;
export type _BinderDetail = Assert<Assignable<Schemas['BinderDetail'], BinderDetail>>;
export type _BinderAddPage = Assert<Assignable<Schemas['AddPageResult'], BinderAddPageResult>>;
export type _BinderPageScan = Assert<Assignable<Schemas['PageScanResult'], BinderPageScanResult>>;
export type _BinderLocation = Assert<Assignable<Schemas['BinderLocation'], BinderLocation>>;
export type _BinderExport = Assert<Assignable<Schemas['BinderExport'], BinderExport>>;
export type _DepositSummary = Assert<Assignable<Schemas['DepositSummary'], DepositSummary>>;
export type _DepositDetail = Assert<Assignable<Schemas['DepositDetail'], DepositDetail>>;
export type _DepositSuggestion = Assert<Assignable<Schemas['Suggestion'], DepositSuggestion>>;
export type _PieceType = Assert<Assignable<Schemas['PieceType'], PieceType>>;

// --- Corps envoyés par le frontend → schémas de requête de l'API
type Sends<Payload, Request> = Payload extends Request ? true : false;
export type _MergeRequest = Assert<Sends<{ duplicate_id: string }, Schemas['ProductMergeRequest']>>;
export type _PieceTypeRequest = Assert<
  Sends<Omit<PieceType, 'id' | 'active'> & { active?: boolean }, Schemas['PieceTypeRequest']>
>;
export type _LoginRequest = Assert<Sends<{ email: string; password: string }, Schemas['LoginRequest']>>;
export type _TransitionRequest = Assert<
  Sends<
    { to: Schemas['WorkflowStatusEnum']; filing_date?: string | null },
    Schemas['RenewalTransitionRequest']
  >
>;
export type _CheckRequest = Assert<
  Sends<
    { amm: string; result: BinderResult; corrections: BinderCorrection[]; note: string },
    Schemas['CheckInputRequest']
  >
>;
export type _RefreshResponse = Assert<Assignable<Schemas['TokenRefresh'], { access: string }>>;
