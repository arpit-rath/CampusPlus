"use client";

/**
 * Student complaint report form.
 *
 * The submit path is deliberately not instant. One request does real work —
 * a multimodal model call, an embedding, a pgvector search, a clustering
 * decision — and hiding that behind a spinner wastes the most persuasive
 * moment in the product. So the button shows the pipeline advancing while
 * the request is in flight, and the result screen says what the system
 * concluded and *why* it concluded it, including whether this report just
 * merged into an existing problem.
 *
 * The stage timings are a paced narration of a request that really is
 * running, not fake progress: the sequence stops advancing at the last stage
 * and only completes when the API actually responds.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError, getStudentId, setStudentId, type Complaint } from "@/lib/api";
import { BUILDING_NAMES, categoryLabel } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";

const STAGES = [
  "Reading your report",
  "Understanding it with AI",
  "Generating an embedding",
  "Searching for similar reports",
  "Scoring priority and routing",
] as const;

const MAX_PHOTO_MB = 5;

export default function ReportPage() {
  const [description, setDescription] = useState("");
  const [building, setBuilding] = useState("");
  const [room, setRoom] = useState("");
  const [studentId, setStudentIdState] = useState("");
  const [photoBase64, setPhotoBase64] = useState<string | undefined>();
  const [photoName, setPhotoName] = useState<string | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Complaint | null>(null);
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setStudentIdState(getStudentId());
  }, []);

  useEffect(() => {
    return () => {
      if (stageTimer.current) clearInterval(stageTimer.current);
    };
  }, []);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      setPhotoBase64(undefined);
      setPhotoName(null);
      setPhotoPreview(null);
      return;
    }
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
      setError(`That photo is over ${MAX_PHOTO_MB} MB — try a smaller one.`);
      e.target.value = "";
      return;
    }

    setError(null);
    setPhotoName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setPhotoBase64(reader.result);
        setPhotoPreview(reader.result);
      }
    };
    reader.onerror = () => {
      setError("Couldn't read that photo — try a different file.");
      setPhotoBase64(undefined);
      setPhotoPreview(null);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!description.trim()) return setError("Describe the problem before submitting.");
    if (description.trim().length < 15)
      return setError("Add a little more detail — a few words won't be enough to route this.");
    if (!building) return setError("Select a building.");

    setSubmitting(true);
    setStage(0);
    stageTimer.current = setInterval(() => {
      // Advance, but stop at the last stage: the request is still running,
      // and pretending otherwise would be lying about progress.
      setStage((current) => Math.min(current + 1, STAGES.length - 1));
    }, 700);

    try {
      const trimmedId = studentId.trim();
      if (trimmedId) setStudentId(trimmedId);

      const complaint = await api.createComplaint({
        description: description.trim(),
        location_building: building,
        location_room: room.trim() || undefined,
        photo_base64: photoBase64,
        student_id: trimmedId || undefined,
      });
      setResult(complaint);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail ?? `Couldn't submit (${err.status}). Is the API running?`
          : "Couldn't reach the API — check that it's running on port 8000.",
      );
    } finally {
      if (stageTimer.current) clearInterval(stageTimer.current);
      setSubmitting(false);
    }
  };

  if (result) {
    return <SubmissionResult complaint={result} onReportAnother={() => {
      setResult(null);
      setDescription("");
      setRoom("");
      setPhotoBase64(undefined);
      setPhotoName(null);
      setPhotoPreview(null);
    }} />;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-8 px-6 py-12">
      <header>
        <Link
          href="/"
          className="font-mono text-xs uppercase tracking-widest text-ink/50 hover:text-ink"
        >
          CampusPlus
        </Link>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">
          What&rsquo;s the problem?
        </h1>
        <p className="mt-3 max-w-md text-ink/70">
          Describe the issue and tell us where it is. We&rsquo;ll categorize it,
          check whether other students have already reported the same thing,
          score its priority, and route it to the right department.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <Field label="Description" htmlFor="description">
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            maxLength={5000}
            disabled={submitting}
            placeholder="e.g. Water is leaking from the ceiling in the Block A hostel corridor and the floor is soaked."
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-ink/30 focus:border-signal disabled:opacity-60"
          />
          <p className="text-right font-mono text-[11px] text-ink/35">
            {description.length}/5000
          </p>
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Building" htmlFor="building">
            <select
              id="building"
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              disabled={submitting}
              className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-signal disabled:opacity-60"
            >
              <option value="">Select a building</option>
              {BUILDING_NAMES.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Room / area" htmlFor="room" optional>
            <input
              id="room"
              type="text"
              value={room}
              maxLength={64}
              onChange={(e) => setRoom(e.target.value)}
              disabled={submitting}
              placeholder="e.g. Room 214"
              className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm text-ink outline-none placeholder:text-ink/30 focus:border-signal disabled:opacity-60"
            />
          </Field>
        </div>

        <Field label="Photo" htmlFor="photo" optional>
          <input
            id="photo"
            type="file"
            accept="image/png,image/jpeg,image/gif,image/webp"
            onChange={handlePhotoChange}
            disabled={submitting}
            className="w-full text-sm text-ink/70 file:mr-3 file:rounded-md file:border-0 file:bg-ink/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink hover:file:bg-ink/15"
          />
          {photoPreview && (
            <div className="mt-2 flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={photoPreview}
                alt="Attached preview"
                className="h-16 w-16 rounded-md border border-ink/10 object-cover"
              />
              <p className="text-xs text-ink/50">
                {photoName}
                <br />
                <span className="text-ink/40">
                  The AI will check this photo against your description.
                </span>
              </p>
            </div>
          )}
        </Field>

        <Field label="Reporting as" htmlFor="student">
          <input
            id="student"
            type="text"
            value={studentId}
            maxLength={255}
            onChange={(e) => setStudentIdState(e.target.value)}
            disabled={submitting}
            placeholder="student_a"
            className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 font-mono text-sm text-ink outline-none focus:border-signal disabled:opacity-60"
          />
          <p className="text-xs text-ink/45">
            Recurring issues are counted per <em>student</em>, not per report —
            so the same person filing three times is one report, not a campus
            trend. Clear this to report anonymously.
          </p>
        </Field>

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical"
          >
            {error}
          </p>
        )}

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-signal px-5 py-2.5 font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Analyzing…" : "Submit report"}
          </button>
          {submitting && <PipelineProgress stage={stage} />}
        </div>
      </form>
    </main>
  );
}

function Field({
  label,
  htmlFor,
  optional,
  children,
}: {
  label: string;
  htmlFor: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
        {optional && <span className="ml-1 font-normal text-ink/40">(optional)</span>}
      </label>
      {children}
    </div>
  );
}

function PipelineProgress({ stage }: { stage: number }) {
  return (
    <div className="flex flex-col gap-1" aria-live="polite">
      <p className="font-mono text-xs text-ink/60">{STAGES[stage]}…</p>
      <div className="flex gap-1">
        {STAGES.map((name, i) => (
          <span
            key={name}
            className={`h-1 w-8 rounded-full transition-colors ${
              i <= stage ? "bg-signal" : "bg-ink/10"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function SubmissionResult({
  complaint,
  onReportAnother,
}: {
  complaint: Complaint;
  onReportAnother: () => void;
}) {
  const merged = complaint.cluster_id !== null;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-calm">
          Report received
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">
          {merged
            ? "You're not the only one."
            : "Thanks — we've logged it."}
        </h1>
        <p className="mt-3 text-ink/70">
          {merged ? (
            <>
              Your report matched an existing problem, so it&rsquo;s been merged
              into a single case rather than opening a duplicate ticket.{" "}
              <strong className="font-semibold text-ink">
                {complaint.independent_student_count} student
                {complaint.independent_student_count === 1 ? "" : "s"}
              </strong>{" "}
              have now reported this
              {complaint.is_recurring && ", which flags it as a recurring issue"}.
            </>
          ) : (
            <>
              This is the first report of its kind here. If others report the
              same thing, they&rsquo;ll be merged into your case and its
              priority will rise automatically.
            </>
          )}
        </p>
      </header>

      <section className="rounded-xl border border-ink/10 bg-white p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
          What the AI understood
        </h2>
        <p className="mt-2 text-ink">{complaint.ai_summary ?? complaint.raw_description}</p>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Fact label="Category" value={categoryLabel(complaint.category_slug)} />
          <Fact label="Routed to" value={complaint.department_name ?? "Unassigned"} />
          <Fact label="Severity" value={`${complaint.severity ?? "—"} / 5`} />
          <Fact
            label="Safety risk"
            value={complaint.safety_flag ? "Flagged" : "No"}
            accent={complaint.safety_flag ? "text-critical" : undefined}
          />
        </dl>

        {complaint.photo_matches_text !== null && (
          <p
            className={`mt-4 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              complaint.photo_matches_text
                ? "bg-calm/10 text-calm"
                : "bg-signal/10 text-signal"
            }`}
          >
            {complaint.photo_matches_text
              ? "Photo verified — it matches your description"
              : "Photo attached, but it didn't clearly match the description"}
          </p>
        )}
      </section>

      <section className="rounded-xl border border-ink/10 bg-white p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink/50">
          Why this priority
        </h2>
        <div className="mt-3">
          <PriorityBar
            breakdown={complaint.priority_breakdown}
            score={complaint.priority_score}
            showLegend
          />
        </div>
      </section>

      <div className="flex flex-wrap gap-3">
        <Link
          href={`/track/${complaint.id}`}
          className="rounded-lg bg-ink px-5 py-2.5 font-medium text-white"
        >
          Track this report
        </Link>
        <button
          onClick={onReportAnother}
          className="rounded-lg border border-ink/20 px-5 py-2.5 font-medium text-ink hover:bg-ink/5"
        >
          Report something else
        </button>
      </div>
    </main>
  );
}

function Fact({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink/40">{label}</dt>
      <dd className={`mt-0.5 font-medium ${accent ?? "text-ink"}`}>{value}</dd>
    </div>
  );
}
