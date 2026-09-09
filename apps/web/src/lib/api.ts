/**
 * Thin typed client over the FastAPI backend. Every fetch in the app should
 * go through here rather than calling fetch() ad hoc — it's the one place
 * that knows the base URL and how to surface API errors consistently.
 *
 * Track C and Track D both extend this file with the endpoints their pages
 * need; keep additions additive (new exported functions/types) rather than
 * restructuring what's here, since both tracks touch this file.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(`${init?.method ?? "GET"} ${path} failed`, res.status);
  }
  return res.json() as Promise<T>;
}

// --- Shared types --------------------------------------------------------
// Mirrors apps/api/app/ai/schemas.py + the complaints table. Keep in sync
// by hand for the hackathon; see packages/shared-types for the longer-term
// OpenAPI-generated version.

export type ComplaintStatus = "open" | "in_progress" | "resolved";

export interface PriorityBreakdown {
  severity: number;
  frequency: number;
  safety: number;
  sla_age: number;
}

export interface Complaint {
  id: string;
  raw_description: string;
  photo_url: string | null;
  location_building: string | null;
  location_room: string | null;
  category_slug: string | null;
  department_name: string | null;
  severity: number;
  safety_flag: boolean;
  priority_score: number;
  priority_breakdown: PriorityBreakdown;
  status: ComplaintStatus;
  ai_summary: string | null;
  is_recurring: boolean;
  cluster_member_count: number;
  created_at: string;
}

export interface CreateComplaintInput {
  description: string;
  location_building: string;
  location_room?: string;
  photo_base64?: string;
}

export const api = {
  health: () => request<{ status: string; llm_provider: string }>("/health"),

  createComplaint: (input: CreateComplaintInput) =>
    request<Complaint>("/complaints", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getComplaint: (id: string) => request<Complaint>(`/complaints/${id}`),

  listComplaints: (params?: { status?: ComplaintStatus }) => {
    const qs = params?.status ? `?status=${params.status}` : "";
    return request<Complaint[]>(`/complaints${qs}`);
  },

  askAdmin: (question: string) =>
    request<{ answer: string; cited_complaint_ids: string[] }>(
      "/admin/ask",
      { method: "POST", body: JSON.stringify({ question }) },
    ),
};
