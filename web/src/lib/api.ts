// The live API and its recorded stand in. The first call on a page probes /v1/health with a six
// second limit; if the API is asleep or unreachable, every API feature on the page answers from
// recorded_session.json for the rest of the visit, and says so beside the control it affects.
import { API, dataUrl } from "./site";

export type Source = "live" | "recorded";

export interface AllocationRow {
  channel: string;
  spend: number;
  last_year: number;
  change: number;
  expected_revenue: number;
  marginal_return: number;
  marginal_profit: number;
  at_bound: string;
  implied_acquisition_cost: number | null;
}

export interface Plan {
  allocation: AllocationRow[];
  expected_revenue: number;
  expected_profit: number;
  profit_lower: number;
  profit_upper: number;
  level: number;
  solver_status: string;
  marginal_equalized: boolean;
  marginal_spread: number;
  interior_channels: number;
  degenerate: boolean;
  degenerate_reason: string | null;
  model_version: string;
  inputs_hash: string;
  spend: Record<string, number>;
}

export interface Envelope {
  statement: string;
  served_at: string;
}
export interface OptimizeResponse extends Envelope {
  plan: Plan;
  stored: boolean;
}
export interface SavedPlanResponse extends Envelope {
  plan_id: string;
  created_at: string;
  plan: Plan;
}
export interface ExperimentResult {
  method: string;
  incremental_revenue: number;
  lower: number;
  upper: number;
  level: number;
  truth: number | null;
  posted_at: string;
}
export interface ExperimentResponse extends Envelope {
  experiment_id: string;
  kind: string;
  name: string;
  plan_hash: string;
  registered_at: string;
  results: ExperimentResult[];
}
export interface HealthResponse extends Envelope {
  status: string;
  model_version: string;
  writes: string;
}

export interface OptimizeBody {
  total_budget: number;
  floor_share?: number;
  ceiling_share?: number;
  max_change_share?: number;
  floors?: Record<string, number>;
  ceilings?: Record<string, number>;
  apply_allowance?: boolean;
  note?: string;
}

interface RecordedResponse {
  method: string;
  path: string;
  status: number;
  request?: unknown;
  body: unknown;
}
export interface RecordedSession {
  recorded: boolean;
  recorded_at: string;
  base_url: string;
  budget_current: number;
  responses: Record<string, RecordedResponse>;
}

export interface Answer<T> {
  source: Source;
  status: number;
  body: T;
  /** Why the answer is the recorded one when the API itself is awake. */
  reason?: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const PROBE_TIMEOUT_MS = 6000;
// The API's machine stops when idle and starts on the first request, which the first probe often
// meets as a 503 or a timeout; one more try after a short pause finds it awake.
const PROBE_ATTEMPTS = 2;
const PROBE_PAUSE_MS = 4000;

let probe: Promise<Source> | null = null;
let session: Promise<RecordedSession> | null = null;

async function probeOnce(): Promise<Source> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetch(`${API}/v1/health`, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) return "recorded";
    const body = (await response.json()) as Partial<HealthResponse>;
    return body.status === "ok" ? "live" : "recorded";
  } catch {
    return "recorded";
  } finally {
    window.clearTimeout(timer);
  }
}

/** Whether this page visit talks to the live API or to the recording. Probed once, then fixed. */
export function apiSource(): Promise<Source> {
  probe ??= (async (): Promise<Source> => {
    if (!API) return "recorded";
    for (let attempt = 1; attempt <= PROBE_ATTEMPTS; attempt += 1) {
      if (attempt > 1) await new Promise((resolve) => window.setTimeout(resolve, PROBE_PAUSE_MS));
      if ((await probeOnce()) === "live") return "live";
    }
    return "recorded";
  })();
  return probe;
}

export function recordedSession(): Promise<RecordedSession> {
  session ??= fetch(dataUrl("recorded_session.json")).then((r) => {
    if (!r.ok) throw new Error(`the recorded session did not load (${r.status})`);
    return r.json() as Promise<RecordedSession>;
  });
  return session;
}

async function fromRecording<T>(name: string, reason?: string): Promise<Answer<T>> {
  const s = await recordedSession();
  const hit = s.responses[name];
  if (!hit) throw new Error(`the recorded session has no response named ${name}`);
  return { source: "recorded", status: hit.status, body: hit.body as T, reason };
}

async function send<T>(path: string, init: RequestInit = {}): Promise<{ status: number; body: T }> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await response.json().catch(() => ({}))) as T & { detail?: string };
  if (!response.ok) throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `status ${response.status}`);
  return { status: response.status, body };
}

/** A read: the live answer when the API is awake, else the recorded one under the given name. */
export async function read<T>(path: string, recordedName: string): Promise<Answer<T>> {
  if ((await apiSource()) === "live") {
    try {
      const { status, body } = await send<T>(path);
      return { source: "live", status, body };
    } catch {
      return fromRecording<T>(recordedName, "the live API did not answer this request");
    }
  }
  return fromRecording<T>(recordedName);
}

/** An optimization on the live API. The caller checks the source first; there is no recording for arbitrary inputs. */
export async function optimize(body: OptimizeBody, signal?: AbortSignal): Promise<OptimizeResponse> {
  const { body: answer } = await send<OptimizeResponse>("/v1/optimize", { method: "POST", body: JSON.stringify(body), signal });
  return answer;
}

/**
 * Save a plan. Writes need the token and a live API; without either, the answer is the plan the
 * recording saved, labeled as such, so the control still shows what a save returns.
 */
export async function savePlan(body: OptimizeBody, token: string): Promise<Answer<SavedPlanResponse>> {
  const source = await apiSource();
  if (source !== "live") return fromRecording<SavedPlanResponse>("save_plan", "the API is asleep");
  if (!token.trim()) return fromRecording<SavedPlanResponse>("save_plan", "no write token was given");
  const { status, body: answer } = await send<SavedPlanResponse>("/v1/plans", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { Authorization: `Bearer ${token.trim()}` },
  });
  return { source: "live", status, body: answer };
}
