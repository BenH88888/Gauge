/**
 * Typed HTTP client for the Gauge FastAPI backend.
 *
 * All communication goes through the session-based flow: create a session,
 * attach a document, confirm plan fields, then query for what-if sweeps and
 * plan Q&A.  The session ID is the single context handle that ties demographics,
 * plan, and document together on the server.
 *
 * The base URL is read from the VITE_API_BASE env var at build time so the
 * same bundle can point at a local dev backend or a deployed one without code
 * changes.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Anonymous user identity
// ---------------------------------------------------------------------------

/**
 * Return the persistent anonymous user ID for this browser, creating one
 * on the first call and storing it in localStorage under `gauge_user_id`.
 *
 * The ID is an opaque UUID sent as `X-Gauge-User-Id` on every request so
 * the backend can scope saved estimates to this browser without requiring
 * a login.  It is not a security credential — it only prevents one user
 * from accidentally seeing another's estimates.
 */
function getOrCreateUserId(): string {
  const STORAGE_KEY = "gauge_user_id";
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

/** Headers included on every request to identify this browser session. */
function authHeaders(): Record<string, string> {
  return { "X-Gauge-User-Id": getOrCreateUserId() };
}

// ---------------------------------------------------------------------------
// Shared primitive types
// ---------------------------------------------------------------------------

export type Sex = "male" | "female";
export type Smoker = "yes" | "no";
export type Region = "northeast" | "midwest" | "south" | "west";

export interface PredictionFeatures {
  age: number;
  sex: Sex;
  bmi: number;
  children: number;
  smoker: Smoker;
  region: Region;
}

/** Raw ML prediction over gross annual charges. */
export interface CostPrediction {
  median_charges_cents: number;
  mean_charges_cents: number;
  lower_bound_cents: number;
  upper_bound_cents: number;
  conformal_calibrated: boolean;
  calibration_coverage: number;
}

/**
 * An 80%-coverage interval for out-of-pocket spend under a specific plan.
 *
 * Derived analytically from the conformal charge interval via the monotone
 * plan cost function — no simulation required.  The coverage guarantee that
 * CQR provides for charges propagates directly to OOP.
 */
export interface OopInterval {
  lower_cents: number;
  median_cents: number;
  upper_cents: number;
  /** Inherited calibration coverage (≈ 0.80). */
  coverage: number | null;
  /** True if the lower bound was capped at the plan OOP max. */
  capped_at_oop_max_lower: boolean;
  /** True if the upper bound was capped at the plan OOP max. */
  capped_at_oop_max_upper: boolean;
}

export type SweepFeature =
  | "age"
  | "sex"
  | "bmi"
  | "children"
  | "smoker"
  | "region";

export interface WhatIfPoint {
  value: number | string;
  prediction: CostPrediction;
  /** Present only when the session has a confirmed plan. */
  oop_interval: OopInterval | null;
}

export interface WhatIfResponse {
  feature: SweepFeature;
  points: WhatIfPoint[];
}

export interface Plan {
  plan_id: string;
  name: string;
  deductible_cents: number;
  out_of_pocket_max_cents: number;
  coinsurance_rate: number;
  copays_cents: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Chat types
// ---------------------------------------------------------------------------

export interface Citation {
  document_id: string;
  chunk_index: number;
  page_numbers: number[];
  snippet: string;
}

export interface ChatResponse {
  document_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  llm_used: string;
}

/** A single completed question/answer exchange, sent back as context on follow-ups. */
export interface ChatTurn {
  question: string;
  answer: string;
}

// ---------------------------------------------------------------------------
// Saved estimate types
// ---------------------------------------------------------------------------

/** A named snapshot of an estimate the user has saved. */
export interface SavedEstimate {
  id: string;
  label: string;
  features: PredictionFeatures;
  plan: Plan | null;
  prediction: CostPrediction;
  oop_interval: OopInterval | null;
  created_at: string;
}

export interface SaveEstimateRequest {
  session_id: string;
  label: string;
}

export interface RenameEstimateRequest {
  label: string;
}

// ---------------------------------------------------------------------------
// Session / guided-flow types
// ---------------------------------------------------------------------------

/**
 * Extracted plan fields returned after uploading a PDF.
 *
 * Any field that is `null` could not be parsed from the document and must be
 * filled in manually by the user on the confirmation form.
 */
export interface PlanDraft {
  deductible_cents: number | null;
  out_of_pocket_max_cents: number | null;
  coinsurance_rate: number | null;
  /** Copay amounts keyed by ServiceCategory string values. */
  copays_cents: Record<string, number>;
  /** Field names that could not be parsed from the document. */
  unresolved_fields: string[];
  /** Human-readable notes about what was or wasn't found. */
  extraction_notes: string[];
}

/** Full personalised estimate combining ML prediction and plan OOP interval. */
export interface SessionEstimate {
  features: PredictionFeatures;
  prediction: CostPrediction;
  plan: Plan | null;
  /** Present once a plan has been confirmed; null otherwise. */
  oop_interval: OopInterval | null;
  document_id: string | null;
}

/** Response from `POST /sessions`. */
export interface CreateSessionResponse {
  session_id: string;
  prediction: CostPrediction;
}

/** Response from `POST /sessions/{id}/document`. */
export interface AttachDocumentResponse {
  document_id: string;
  plan_draft: PlanDraft;
}

/** Request body for `POST /sessions/{id}/plan`. */
export interface ConfirmPlanRequest {
  deductible_cents: number;
  out_of_pocket_max_cents: number;
  coinsurance_rate: number;
  copays_cents: Record<string, number>;
  plan_name: string;
}

// ---------------------------------------------------------------------------
// HTTP helpers (internal)
// ---------------------------------------------------------------------------

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Format a cent amount as a US dollar currency string.
 *
 * @param cents - Amount in whole US cents.
 * @returns Formatted string, e.g. `"$1,500"`.
 */
export function centsToDollars(cents: number): string {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

// ---------------------------------------------------------------------------
// Session API
// ---------------------------------------------------------------------------

/**
 * Create a new session from the user's demographic inputs.
 *
 * @param features - User demographics (age, BMI, smoker status, etc.).
 * @returns New session ID and a first-pass cost prediction.
 */
export function createSession(
  features: PredictionFeatures,
): Promise<CreateSessionResponse> {
  return postJSON<CreateSessionResponse>("/sessions", { features });
}

/**
 * Upload a plan PDF and attach it to an existing session.
 *
 * The server automatically extracts plan fields (deductible, OOP max, etc.)
 * from the document and returns a draft for the user to review.
 *
 * @param sessionId - Session to attach the document to.
 * @param file - The PDF file chosen by the user.
 * @returns The new document ID and the auto-extracted plan draft.
 * @throws {Error} On network failure or a non-2xx response.
 */
export async function attachSessionDocument(
  sessionId: string,
  file: File,
): Promise<AttachDocumentResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/document`,
    { method: "POST", headers: authHeaders(), body: form },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<AttachDocumentResponse>;
}

/**
 * Confirm (or correct) the plan fields and receive the full estimate.
 *
 * @param sessionId - Target session.
 * @param req - User-reviewed plan fields.
 * @returns Full personalised estimate with OOP interval.
 */
export function confirmSessionPlan(
  sessionId: string,
  req: ConfirmPlanRequest,
): Promise<SessionEstimate> {
  return postJSON<SessionEstimate>(
    `/sessions/${encodeURIComponent(sessionId)}/plan`,
    req,
  );
}

/**
 * Run a what-if sweep using the session's demographics as the baseline.
 *
 * @param sessionId - Target session.
 * @param feature - Feature to vary (e.g. `"age"`, `"smoker"`).
 * @param values - Values to sweep the feature across.
 * @returns Prediction at each swept value, with OOP interval if the session
 *   has a confirmed plan.
 */
export function sessionWhatIf(
  sessionId: string,
  feature: SweepFeature,
  values: Array<number | string>,
): Promise<WhatIfResponse> {
  return postJSON<WhatIfResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/whatif`,
    { feature, values },
  );
}

/**
 * Ask a plain-English question against the session's uploaded plan document.
 *
 * @param sessionId - Target session (must have an attached document).
 * @param question - Free-text question from the user.
 * @param history - Prior turns in this conversation (oldest first) so the LLM
 *   can give contextually coherent follow-up answers.
 * @param topK - Number of chunks to retrieve for context. Defaults to 4.
 * @returns Answer text and page-level citations.
 */
export function sessionChat(
  sessionId: string,
  question: string,
  history: ChatTurn[] = [],
  topK = 4,
): Promise<ChatResponse> {
  return postJSON<ChatResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/chat`,
    { question, history, top_k: topK },
  );
}

// ---------------------------------------------------------------------------
// Saved estimates API
// ---------------------------------------------------------------------------

/** Save the current session's estimate under a user-supplied label. */
export function saveEstimate(req: SaveEstimateRequest): Promise<SavedEstimate> {
  return postJSON<SavedEstimate>("/saved-estimates", req);
}

/** List all saved estimates owned by this browser session, newest first. */
export async function listSavedEstimates(): Promise<SavedEstimate[]> {
  const res = await fetch(`${BASE}/saved-estimates`, { headers: authHeaders() });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<SavedEstimate[]>;
}

/** Rename a saved estimate owned by this browser session. */
export async function renameSavedEstimate(
  id: string,
  req: RenameEstimateRequest,
): Promise<SavedEstimate> {
  const res = await fetch(`${BASE}/saved-estimates/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<SavedEstimate>;
}

/** Delete a saved estimate owned by this browser session. */
export async function deleteSavedEstimate(id: string): Promise<void> {
  const res = await fetch(`${BASE}/saved-estimates/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
}
