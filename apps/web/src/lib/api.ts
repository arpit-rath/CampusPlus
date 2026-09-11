/**
 * Typed client over the FastAPI backend. Every fetch in the app goes through
 * here — it is the one place that knows the base URL, how admin auth is
 * attached, and how API errors surface.
 *
 * The types below mirror `apps/api/app/routers/*.py` field for field. They
 * are hand-maintained during the hackathon; `packages/shared-types` explains
 * how to regenerate them from the OpenAPI schema when that is worth doing.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const ADMIN_TOKEN_STORAGE_KEY = "campusplus.adminToken";
const STUDENT_ID_STORAGE_KEY = "campusplus.studentId";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string,
  ) {
    super(message);
  }
}

/**
 * The admin token is deliberately kept in localStorage and typed in by the
 * operator, not baked into the bundle via NEXT_PUBLIC_*. A shared secret in
 * a public env var is shipped to every visitor, which would make the whole
 * check theatre.
 */
export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
  } catch {
    /* private browsing — the header is simply omitted */
  }
}

/**
 * A stable per-browser reporter id.
 *
 * This matters more than it looks: recurring detection counts *independent
 * students*, so the identity a complaint is filed under is what decides
 * whether three reports become a recurring issue or one person repeating
 * themselves. Generating and remembering one per browser makes the demo
 * honest — and the report form lets you edit it, so one machine can play
 * several students.
 */
export function getStudentId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(STUDENT_ID_STORAGE_KEY);
    if (existing) return existing;
    const generated = `student_${Math.random().toString(36).slice(2, 8)}`;
    window.localStorage.setItem(STUDENT_ID_STORAGE_KEY, generated);
    return generated;
  } catch {
    return `student_${Math.random().toString(36).slice(2, 8)}`;
  }
}

export function setStudentId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STUDENT_ID_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { admin?: boolean },
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  if (init?.admin) {
    const token = getAdminToken();
    if (token) headers["X-Admin-Token"] = token;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    // Surface the API's own message where there is one — "photo is not a
    // recognized image" is far more useful to a student than "422".
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      detail ?? `${init?.method ?? "GET"} ${path} failed`,
      res.status,
      detail,
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- Types ---------------------------------------------------------------

export type ComplaintStatus = "open" | "in_progress" | "resolved";

export interface PriorityBreakdown {
  severity: number;
  frequency: number;
  safety: number;
  sla_age: number;
}

export interface Complaint {
  id: string;
  student_id: string | null;
  raw_description: string;
  photo_url: string | null;
  /** null = no photo attached; true/false = the model's verdict on whether
   *  the photo corroborates the text. */
  photo_matches_text: boolean | null;
  location_building: string | null;
  location_room: string | null;
  category_slug: string | null;
  department_id: string | null;
  department_name: string | null;
  severity: number | null;
  safety_flag: boolean;
  priority_score: number;
  priority_breakdown: PriorityBreakdown;
  status: ComplaintStatus;
  ai_summary: string | null;
  cluster_id: string | null;
  is_recurring: boolean;
  cluster_member_count: number;
  independent_student_count: number;
  suggested_match_complaint_id: string | null;
  suggested_similarity: number | null;
  department_overridden: boolean;
  created_at: string;
}

export interface Cluster {
  id: string;
  category_slug: string | null;
  location_building: string | null;
  member_count: number;
  independent_student_count: number;
  is_recurring: boolean;
  first_seen: string;
  last_seen: string;
  representative_complaint_id: string | null;
  representative_summary: string | null;
  max_priority_score: number;
  safety_flag: boolean;
}

export interface ClusterDetail extends Cluster {
  members: Complaint[];
}

export interface StatusEvent {
  id: string;
  status: ComplaintStatus;
  note: string | null;
  actor: string | null;
  created_at: string;
}

export interface Department {
  id: string;
  name: string;
  contact_email: string;
}

export interface SuggestedMerge {
  complaint: Complaint;
  target: Complaint;
  similarity: number;
}

export interface AskAnswer {
  answer: string;
  cited_complaint_ids: string[];
  /** How the backend read the question — shown to the admin so the
   *  filtering is auditable rather than magic. */
  filters: string;
  matched_count: number;
  /** False when the question was not about campus complaints at all, so the
   *  answer is a refusal rather than a finding. */
  in_scope?: boolean;
}

export interface AdminStats {
  open: number;
  in_progress: number;
  resolved: number;
  clusters: number;
  recurring_clusters: number;
  safety_flagged: number;
  pending_merges: number;
  realtime_subscribers: number;
}

export interface Digest {
  generated_at: string;
  window_days: number;
  total_complaints: number;
  resolved_complaints: number;
  recurring_clusters: number;
  safety_flagged: number;
  top_buildings: { label: string; value: string }[];
  top_categories: { label: string; value: string }[];
  headline_issues: Complaint[];
}

export interface ChaosResult {
  submitted: number;
  merged: number;
  new_clusters_recurring: number;
}

export interface Health {
  status: string;
  llm_provider: string;
  llm_effective: string;
  llm_fallback_to_mock: boolean;
  admin_auth: "enabled" | "disabled";
  realtime_subscribers: number;
  thresholds: {
    duplicate: number;
    suggested_merge: number;
    recurring_students: number;
    window_days: number;
  };
}

export interface CreateComplaintInput {
  description: string;
  location_building: string;
  location_room?: string;
  photo_base64?: string;
  student_id?: string;
}

export interface ComplaintListFilters {
  status?: ComplaintStatus;
  category?: string;
  building?: string;
  recurring_only?: boolean;
}

function query(params: Record<string, string | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === false || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/** Absolute URL for a photo path the API returned (`/uploads/...`). */
export function photoUrl(path: string | null): string | null {
  if (!path) return null;
  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

export const api = {
  health: () => request<Health>("/health"),

  createComplaint: (input: CreateComplaintInput) =>
    request<Complaint>("/complaints", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getComplaint: (id: string) => request<Complaint>(`/complaints/${id}`),

  listComplaints: (filters?: ComplaintListFilters) =>
    request<Complaint[]>(`/complaints${query({ ...filters })}`),

  listStatusEvents: (id: string) =>
    request<StatusEvent[]>(`/complaints/${id}/events`),

  listClusters: (recurringOnly = false) =>
    request<Cluster[]>(`/clusters${query({ recurring_only: recurringOnly })}`),

  getCluster: (id: string) => request<ClusterDetail>(`/clusters/${id}`),

  listDepartments: () => request<Department[]>("/departments"),

  // --- admin ---
  updateStatus: (
    id: string,
    body: { status: ComplaintStatus; note?: string; actor?: string },
  ) =>
    request<Complaint>(`/complaints/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify(body),
      admin: true,
    }),

  overrideRoute: (
    id: string,
    body: { department_id?: string; category_slug?: string; note?: string },
  ) =>
    request<Complaint>(`/admin/complaints/${id}/route`, {
      method: "PATCH",
      body: JSON.stringify(body),
      admin: true,
    }),

  listSuggestedMerges: () =>
    request<SuggestedMerge[]>("/admin/suggested-merges", { admin: true }),

  resolveSuggestedMerge: (id: string, accept: boolean) =>
    request<Complaint>(`/admin/complaints/${id}/merge`, {
      method: "POST",
      body: JSON.stringify({ accept }),
      admin: true,
    }),

  unmergeComplaint: (id: string) =>
    request<Complaint>(`/admin/complaints/${id}/unmerge`, {
      method: "POST",
      admin: true,
    }),

  askAdmin: (question: string) =>
    request<AskAnswer>("/admin/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
      admin: true,
    }),

  adminStats: () => request<AdminStats>("/admin/stats", { admin: true }),

  digest: (windowDays = 7) =>
    request<Digest>(`/admin/digest?window_days=${windowDays}`, { admin: true }),

  chaos: (count = 6) =>
    request<ChaosResult>("/admin/chaos", {
      method: "POST",
      body: JSON.stringify({ count }),
      admin: true,
    }),
};

// --- Realtime -------------------------------------------------------------

export type RealtimeEvent =
  | { type: "connected"; data: { ok: boolean } }
  | {
      type: "complaint.created";
      data: {
        complaint: Complaint;
        similarity_label: "duplicate" | "suggested_merge" | "new";
        best_match_id: string | null;
        best_match_score: number | null;
      };
    }
  | { type: "complaint.updated"; data: { complaint?: Complaint; deleted_id?: string } }
  | {
      type: "cluster.updated" | "cluster.recurring";
      data: {
        cluster_id: string;
        member_count: number;
        independent_student_count: number;
        is_recurring: boolean;
        location_building: string | null;
      };
    };

/**
 * Subscribe to the backend's `/ws/complaints` feed.
 *
 * Reconnects with a capped backoff, because the demo cannot afford a
 * dashboard that goes permanently silent because the API restarted once.
 * Returns a teardown function; `onStatus` lets the UI show honestly whether
 * it is live or reconnecting rather than quietly showing stale data.
 */
export function subscribeToRealtime(
  onEvent: (event: RealtimeEvent) => void,
  onStatus?: (status: "connecting" | "live" | "offline") => void,
): () => void {
  let socket: WebSocket | null = null;
  let retryDelay = 1000;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const url = `${API_BASE_URL.replace(/^http/, "ws")}/ws/complaints`;

  const connect = () => {
    if (closed) return;
    onStatus?.("connecting");
    try {
      socket = new WebSocket(url);
    } catch {
      scheduleRetry();
      return;
    }

    socket.onopen = () => {
      retryDelay = 1000;
      onStatus?.("live");
    };
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as RealtimeEvent);
      } catch {
        /* ignore a malformed frame rather than tearing down the feed */
      }
    };
    socket.onerror = () => socket?.close();
    socket.onclose = () => {
      onStatus?.("offline");
      scheduleRetry();
    };
  };

  const scheduleRetry = () => {
    if (closed) return;
    retryTimer = setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 15000);
  };

  connect();

  return () => {
    closed = true;
    if (retryTimer) clearTimeout(retryTimer);
    socket?.close();
  };
}
