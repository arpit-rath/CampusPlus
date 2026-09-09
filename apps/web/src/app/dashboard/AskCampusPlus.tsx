"use client";

/**
 * Ask CampusPlus — natural-language querying over the complaint corpus.
 *
 * Two deliberate UI choices, both about trust:
 *
 * 1. The backend returns how it *interpreted* the question (`filters`), and
 *    this shows it. An answer box that just talks is a box you have to take
 *    on faith; showing "category wifi, in Innovation Hall, last 7 day(s)"
 *    lets an operator see the question was read correctly before acting.
 * 2. Citations are rendered as links to the actual complaints. The API
 *    guarantees every cited id belongs to a row it really fetched, so these
 *    always resolve — the answer is checkable, not just plausible.
 */

import { useState } from "react";
import Link from "next/link";
import { api, ApiError, type AskAnswer, type Complaint } from "@/lib/api";

const EXAMPLES = [
  "Which building has the most urgent recurring problems?",
  "Any safety issues this week?",
  "What wifi complaints are still open?",
];

export function AskCampusPlus({ complaints }: { complaints: Complaint[] }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const byId = new Map(complaints.map((c) => [c.id, c]));

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setAsking(true);
    setError(null);
    try {
      setAnswer(await api.askAdmin(trimmed));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "This needs an admin token — enter it above."
          : "Couldn't reach the API. Is it running?",
      );
      setAnswer(null);
    } finally {
      setAsking(false);
    }
  };

  return (
    <section className="flex h-full flex-col rounded-xl border border-ink/10 bg-white p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink">
        Ask CampusPlus
      </h2>
      <p className="mt-0.5 text-xs text-ink/50">
        Answered only from real complaint records — never from a model&rsquo;s
        memory, and never by letting it write a query.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="mt-3 flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          disabled={asking}
          placeholder="Ask about the campus…"
          className="min-w-0 flex-1 rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm outline-none placeholder:text-ink/30 focus:border-signal disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={asking || !question.trim()}
          className="shrink-0 rounded-lg bg-ink px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {asking ? "…" : "Ask"}
        </button>
      </form>

      {!answer && !error && !asking && (
        <ul className="mt-3 flex flex-col gap-1.5">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                onClick={() => {
                  setQuestion(example);
                  ask(example);
                }}
                className="w-full rounded-md border border-ink/10 px-2.5 py-1.5 text-left text-xs text-ink/60 transition-colors hover:border-ink/25 hover:text-ink"
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      )}

      {asking && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="h-3 w-3/4 animate-pulse rounded bg-ink/10" />
          <div className="h-3 w-full animate-pulse rounded bg-ink/10" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-ink/10" />
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-critical/25 bg-critical/5 px-3 py-2 text-xs text-critical">
          {error}
        </p>
      )}

      {answer && !asking && (
        <div className="mt-3 flex min-h-0 flex-1 flex-col gap-2">
          <p className="text-sm leading-relaxed text-ink">{answer.answer}</p>

          <p className="font-mono text-[10px] uppercase tracking-wide text-ink/35">
            Read as: {answer.filters} · {answer.matched_count} record
            {answer.matched_count === 1 ? "" : "s"} matched
          </p>

          {answer.cited_complaint_ids.length > 0 && (
            <div className="flex min-h-0 flex-col gap-1 overflow-y-auto">
              <p className="text-[11px] font-medium uppercase tracking-wide text-ink/45">
                Based on
              </p>
              {answer.cited_complaint_ids.slice(0, 6).map((id) => {
                const complaint = byId.get(id);
                return (
                  <Link
                    key={id}
                    href={`/track/${id}`}
                    className="truncate rounded border border-ink/10 px-2 py-1 font-mono text-[11px] text-ink/60 hover:border-ink/25 hover:text-ink"
                  >
                    #{id.slice(0, 8)}
                    {complaint && (
                      <span className="ml-1.5 font-sans text-ink/45">
                        {complaint.ai_summary ?? complaint.raw_description}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
