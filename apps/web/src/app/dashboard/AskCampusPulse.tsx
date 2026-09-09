/**
 * "Ask CampusPluse" — natural-language query box over the admin data
 * (build-plan.md §6, §7, §11 demo script). Calls api.askAdmin() and
 * renders the answer with its cited complaints as linkable chips.
 *
 * ASSUMPTION: `cited_complaint_ids` are ids resolvable at the student
 * tracker route `/track/[id]` (Track C's route) — reused here per the
 * task brief rather than building a separate admin detail view.
 */

"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

interface AskResult {
  answer: string;
  cited_complaint_ids: string[];
}

export function AskCampusPulse() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    try {
      const res = await api.askAdmin(trimmed);
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`The API rejected that question (status ${err.status}).`);
      } else {
        setError(
          "Couldn't reach CampusPluse — is the backend running?",
        );
      }
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="flex h-full flex-col rounded-lg border border-ink/10 bg-white p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
        Ask CampusPluse
      </h2>
      <p className="mt-0.5 text-xs text-ink/50">
        Ask a question about current complaints in plain language
      </p>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What's trending in the hostel block this week?"
          className="min-w-0 flex-1 rounded-md border border-ink/20 bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink/40 focus:border-signal focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="shrink-0 rounded-md bg-signal px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>

      <div className="mt-3 flex-1">
        {loading && (
          <p className="text-sm text-ink/50">Thinking through the data…</p>
        )}

        {!loading && error && (
          <p className="rounded-md bg-critical/10 px-3 py-2 text-sm text-critical">
            {error}
          </p>
        )}

        {!loading && !error && result && (
          <div className="rounded-md bg-ink/5 px-3 py-2">
            <p className="text-sm text-ink">{result.answer}</p>
            {result.cited_complaint_ids.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {result.cited_complaint_ids.map((id) => (
                  <Link
                    key={id}
                    href={`/track/${id}`}
                    className="rounded-full border border-ink/20 bg-white px-2 py-0.5 font-mono text-[10px] text-ink/60 hover:border-signal hover:text-signal"
                  >
                    #{id.slice(0, 8)}
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}

        {!loading && !error && !result && (
          <p className="text-sm text-ink/40">
            Answers cite the complaints they're based on.
          </p>
        )}
      </div>
    </section>
  );
}
