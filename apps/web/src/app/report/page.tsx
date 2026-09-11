"use client";

/**
 * Complaint report form.
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
 *
 * Validation follows the pattern the UX rules ask for, in all three places
 * it has to exist to be useful: a required marker before you type, an inline
 * message under the field that failed wired up with `aria-describedby`, and
 * a summary at the top of the form that takes focus after a failed submit
 * and links to each bad field. A red border on its own tells someone who
 * cannot see colour nothing at all, and a summary on its own makes them hunt
 * for which of nine fields it meant.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError, setStudentId, type Complaint } from "@/lib/api";
import { BUILDING_NAMES, categoryLabel } from "@/lib/campus";
import { PriorityBar } from "@/components/PriorityBar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BrandMark } from "@/components/icons";

const STAGES = [
  "Reading your report",
  "Understanding it with AI",
  "Generating an embedding",
  "Searching for similar reports",
  "Scoring priority and routing",
] as const;

const MAX_PHOTO_MB = 5;
const MIN_DESCRIPTION = 15;

const ROLES = [
  { value: "student", label: "Student" },
  { value: "teacher", label: "Teacher" },
] as const;

type Role = (typeof ROLES)[number]["value"];

type FieldName = "description" | "building" | "room" | "role" | "name";

const FIELD_LABELS: Record<FieldName, string> = {
  description: "Description",
  building: "Building",
  room: "Room / area",
  role: "Reporting as",
  name: "Your name",
};

const NAME_KEY = "campusplus.reporterName";
const ROLE_KEY = "campusplus.reporterRole";

function readStored(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? "";
  } catch {
    return ""; // private browsing: the convenience is lost, nothing else
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/**
 * The identity a complaint is filed under.
 *
 * Recurring detection counts *distinct reporters*, so this is what decides
 * whether three reports are a campus-wide pattern or one person filing three
 * times. Deriving it from the name means the same person counts once even
 * from a different browser, which the old random per-browser id could not
 * do. Two different people who share a name collapse into one — that
 * under-counts reporters, which is the safe direction: it can make the
 * system slower to call something recurring, never quicker.
 */
function reporterKey(role: string, name: string): string {
  return `${role}:${name.trim().toLowerCase().replace(/\s+/g, "-")}`;
}

export default function ReportPage() {
  const [description, setDescription] = useState("");
  const [building, setBuilding] = useState("");
  const [room, setRoom] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const [name, setName] = useState("");
  const [photoBase64, setPhotoBase64] = useState<string | undefined>();
  const [photoName, setPhotoName] = useState<string | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  // A counter, not a boolean: a second failed submit has to move focus back
  // to the summary, and a flag that is already true does not change.
  const [failedSubmits, setFailedSubmits] = useState(0);

  const [submitting, setSubmitting] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Complaint | null>(null);

  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const storedRole = readStored(ROLE_KEY);
    if (storedRole === "student" || storedRole === "teacher") setRole(storedRole);
    setName(readStored(NAME_KEY));
  }, []);

  useEffect(() => {
    return () => {
      if (stageTimer.current) clearInterval(stageTimer.current);
    };
  }, []);

  useEffect(() => {
    if (failedSubmits > 0) summaryRef.current?.focus();
  }, [failedSubmits]);

  // --- validation -------------------------------------------------------

  const validate = (field: FieldName, values = { description, building, room, role, name }) => {
    switch (field) {
      case "description":
        if (!values.description.trim()) return "Describe the problem.";
        if (values.description.trim().length < MIN_DESCRIPTION)
          return `Add a little more detail — at least ${MIN_DESCRIPTION} characters, so it can be routed.`;
        return null;
      case "building":
        return values.building ? null : "Select the building.";
      case "room":
        return values.room.trim() ? null : "Say which room or area — a building alone is too broad to fix.";
      case "role":
        return values.role ? null : "Select whether you are a student or a teacher.";
      case "name":
        if (!values.name.trim()) return "Enter your name.";
        if (values.name.trim().length < 2) return "Enter your full name.";
        return null;
    }
  };

  /** Validate on blur, which is late enough not to nag mid-typing. */
  const handleBlur = (field: FieldName) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setErrors((prev) => ({ ...prev, [field]: validate(field) ?? undefined }));
  };

  /** Clear a field's error as soon as it becomes valid, never introduce one. */
  const revalidate = (field: FieldName, values: Parameters<typeof validate>[1]) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = validate(field, values);
      if (next) return prev;
      const cleared = { ...prev };
      delete cleared[field];
      return cleared;
    });
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    const values = { description, building, room, role, name };
    const found: Partial<Record<FieldName, string>> = {};
    (Object.keys(FIELD_LABELS) as FieldName[]).forEach((field) => {
      const message = validate(field, values);
      if (message) found[field] = message;
    });

    if (Object.keys(found).length > 0) {
      setErrors(found);
      setTouched({ description: true, building: true, room: true, role: true, name: true });
      // Focus moves to the summary rather than the first bad field: it says
      // how many problems there are, and each entry links to its own field.
      // Done in an effect above, because the node does not exist until React
      // has rendered the state this line is setting.
      setFailedSubmits((n) => n + 1);
      return;
    }

    setSubmitting(true);
    setStage(0);
    stageTimer.current = setInterval(() => {
      // Advance, but stop at the last stage: the request is still running,
      // and pretending otherwise would be lying about progress.
      setStage((current) => Math.min(current + 1, STAGES.length - 1));
    }, 700);

    try {
      const trimmedName = name.trim();
      writeStored(NAME_KEY, trimmedName);
      writeStored(ROLE_KEY, role);

      const identity = reporterKey(role, trimmedName);
      setStudentId(identity);

      const complaint = await api.createComplaint({
        description: description.trim(),
        location_building: building,
        location_room: room.trim(),
        photo_base64: photoBase64,
        student_id: identity,
        reporter_name: trimmedName,
        reporter_role: role as Role,
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

  if (result) {
    return (
      <SubmissionResult
        complaint={result}
        onReportAnother={() => {
          setResult(null);
          setDescription("");
          setRoom("");
          setPhotoBase64(undefined);
          setPhotoName(null);
          setPhotoPreview(null);
          setErrors({});
          setTouched({});
          setFailedSubmits(0);
        }}
      />
    );
  }

  const invalidFields = (Object.keys(errors) as FieldName[]).filter((f) => errors[f]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-8 px-4 py-6 sm:px-6 sm:py-10">
      <PageBar />

      <header>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          What&rsquo;s the problem?
        </h1>
        <p className="mt-3 max-w-lg leading-relaxed text-muted">
          Describe the issue and tell us where it is. We&rsquo;ll categorize it,
          check whether anyone has already reported the same thing, score its
          priority, and route it to the right department.
        </p>
      </header>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
        {failedSubmits > 0 && invalidFields.length > 0 && (
          <div
            ref={summaryRef}
            role="alert"
            tabIndex={-1}
            aria-labelledby="error-summary-title"
            className="rounded-xl border border-critical/40 bg-critical/[0.07] px-4 py-3 outline-none"
          >
            <h2 id="error-summary-title" className="text-sm font-semibold text-critical">
              {invalidFields.length === 1
                ? "There is one thing to fix"
                : `There are ${invalidFields.length} things to fix`}
            </h2>
            <ul className="mt-1.5 flex flex-col gap-1">
              {invalidFields.map((field) => (
                <li key={field}>
                  <a
                    href={`#${field}`}
                    className="text-xs font-medium text-critical underline underline-offset-2 hover:no-underline"
                  >
                    {FIELD_LABELS[field]}: {errors[field]}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        <fieldset className="panel flex flex-col gap-5 p-4 sm:p-5" disabled={submitting}>
          <legend className="panel-legend">The problem</legend>

          <Field
            name="description"
            label={FIELD_LABELS.description}
            error={touched.description ? errors.description : undefined}
            hint="What is wrong, and what does it affect?"
            counter={`${description.length}/5000`}
          >
            <textarea
              id="description"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                revalidate("description", { description: e.target.value, building, room, role, name });
              }}
              onBlur={() => handleBlur("description")}
              rows={5}
              maxLength={5000}
              aria-required="true"
              aria-invalid={Boolean(touched.description && errors.description)}
              aria-describedby={describedBy("description", touched.description && errors.description, true)}
              placeholder="e.g. Water is leaking from the ceiling in the Block A hostel corridor and the floor is soaked."
              className="input resize-y"
            />
          </Field>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field
              name="building"
              label={FIELD_LABELS.building}
              error={touched.building ? errors.building : undefined}
            >
              <select
                id="building"
                value={building}
                onChange={(e) => {
                  setBuilding(e.target.value);
                  revalidate("building", { description, building: e.target.value, room, role, name });
                }}
                onBlur={() => handleBlur("building")}
                aria-required="true"
                aria-invalid={Boolean(touched.building && errors.building)}
                aria-describedby={describedBy("building", touched.building && errors.building)}
                className="input"
              >
                <option value="">Select a building</option>
                {BUILDING_NAMES.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              name="room"
              label={FIELD_LABELS.room}
              error={touched.room ? errors.room : undefined}
              hint="Room number, floor, or a landmark."
            >
              <input
                id="room"
                type="text"
                value={room}
                maxLength={64}
                onChange={(e) => {
                  setRoom(e.target.value);
                  revalidate("room", { description, building, room: e.target.value, role, name });
                }}
                onBlur={() => handleBlur("room")}
                aria-required="true"
                aria-invalid={Boolean(touched.room && errors.room)}
                aria-describedby={describedBy("room", touched.room && errors.room, true)}
                placeholder="e.g. Room 214, second-floor corridor"
                className="input"
              />
            </Field>
          </div>

          <Field name="photo" label="Photo" optional hint="Checked against your description by the model.">
            <input
              id="photo"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              onChange={handlePhotoChange}
              className="w-full cursor-pointer text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-ink/10 file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink file:transition-colors hover:file:bg-ink/15"
            />
            {photoPreview && (
              <div className="mt-1 flex items-center gap-3 rounded-lg border border-ink/10 bg-ink/[0.02] p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={photoPreview}
                  alt="Attached preview"
                  className="h-14 w-14 shrink-0 rounded-md border border-ink/10 object-cover"
                />
                <p className="min-w-0 flex-1 truncate text-xs text-muted">{photoName}</p>
              </div>
            )}
          </Field>
        </fieldset>

        <fieldset className="panel flex flex-col gap-5 p-4 sm:p-5" disabled={submitting}>
          <legend className="panel-legend">Who is reporting</legend>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field
              name="role"
              label={FIELD_LABELS.role}
              error={touched.role ? errors.role : undefined}
            >
              <select
                id="role"
                value={role}
                onChange={(e) => {
                  const next = e.target.value as Role | "";
                  setRole(next);
                  revalidate("role", { description, building, room, role: next, name });
                }}
                onBlur={() => handleBlur("role")}
                aria-required="true"
                aria-invalid={Boolean(touched.role && errors.role)}
                aria-describedby={describedBy("role", touched.role && errors.role)}
                className="input"
              >
                <option value="">Select one</option>
                {ROLES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              name="name"
              label={FIELD_LABELS.name}
              error={touched.name ? errors.name : undefined}
            >
              <input
                id="name"
                type="text"
                value={name}
                maxLength={255}
                autoComplete="name"
                onChange={(e) => {
                  setName(e.target.value);
                  revalidate("name", { description, building, room, role, name: e.target.value });
                }}
                onBlur={() => handleBlur("name")}
                aria-required="true"
                aria-invalid={Boolean(touched.name && errors.name)}
                aria-describedby={describedBy("name", touched.name && errors.name)}
                placeholder="e.g. Arpit Rath"
                className="input"
              />
            </Field>
          </div>

          <p className="field-hint">
            Recurring issues are counted per <em>reporter</em>, not per report —
            the same person filing three times is one problem, not a campus
            trend. Your name is visible to the facilities team handling the
            report.
          </p>
        </fieldset>

        {error && (
          <p
            role="alert"
            className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical"
          >
            {error}
          </p>
        )}

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <button type="submit" disabled={submitting} className="btn btn-primary px-6">
            {submitting ? "Analyzing…" : "Submit report"}
          </button>
          {submitting && <PipelineProgress stage={stage} />}
        </div>
      </form>
    </main>
  );
}

/**
 * `aria-describedby` for a field: its error first, then its hint.
 *
 * The hint id is only included when the hint is actually on screen — `Field`
 * swaps the hint out for the error, and a dangling reference is a broken
 * announcement rather than a harmless one.
 */
function describedBy(name: string, error: unknown, hasHint = false): string | undefined {
  const ids = [
    error ? `${name}-error` : null,
    hasHint && !error ? `${name}-hint` : null,
  ].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function PageBar() {
  return (
    <div className="flex items-center justify-between gap-3">
      <Link
        href="/"
        className="inline-flex items-center gap-2 text-muted transition-colors hover:text-ink"
      >
        <BrandMark className="h-[18px] w-[18px] text-signal-ink" />
        <span className="font-mono text-xs uppercase tracking-widest">CampusPlus</span>
      </Link>
      <ThemeToggle />
    </div>
  );
}

function Field({
  name,
  label,
  optional,
  hint,
  error,
  counter,
  children,
}: {
  name: string;
  label: string;
  optional?: boolean;
  hint?: string;
  error?: string;
  /** Optional right-aligned figure, such as a character count. */
  counter?: string;
  children: React.ReactNode;
}) {
  const message = error ? (
    <p id={`${name}-error`} className="field-error">
      {error}
    </p>
  ) : hint ? (
    <p id={`${name}-hint`} className="field-hint">
      {hint}
    </p>
  ) : null;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="field-label">
        {label}
        {optional ? (
          <span className="ml-1.5 font-normal text-muted">(optional)</span>
        ) : (
          <span className="ml-1 text-critical" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {/* One row, not two stacked ones: the message reads from the left edge
          of the field and the counter sits against its right edge, so the
          block under a field has the same two alignment points every time
          rather than alternating between them. */}
      {(message || counter) && (
        <div className="flex items-baseline justify-between gap-3">
          <span className="min-w-0">{message}</span>
          {counter && (
            <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted">
              {counter}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineProgress({ stage }: { stage: number }) {
  return (
    <div className="flex flex-col gap-1.5" aria-live="polite">
      <p className="font-mono text-xs text-muted">{STAGES[stage]}…</p>
      <div className="flex gap-1">
        {STAGES.map((name, i) => (
          <span
            key={name}
            className={`h-1 w-8 rounded-full transition-colors duration-300 ${
              i <= stage ? "bg-signal" : "bg-ink/15"
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
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-10">
      <PageBar />

      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-calm">
          Report received
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
          {merged ? "You're not the only one." : "Thanks — we've logged it."}
        </h1>
        <p className="mt-3 leading-relaxed text-muted">
          {merged ? (
            <>
              Your report matched an existing problem, so it&rsquo;s been merged
              into a single case rather than opening a duplicate ticket.{" "}
              <strong className="font-semibold text-ink">
                {complaint.independent_student_count} reporter
                {complaint.independent_student_count === 1 ? "" : "s"}
              </strong>{" "}
              have now raised this
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

      <section className="panel p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-muted">
          What the AI understood
        </h2>
        <p className="mt-2 leading-relaxed text-ink">
          {complaint.ai_summary ?? complaint.raw_description}
        </p>

        <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
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
            className={`mt-5 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
              complaint.photo_matches_text
                ? "bg-calm/10 text-calm"
                : "bg-signal/10 text-signal-ink"
            }`}
          >
            {complaint.photo_matches_text
              ? "Photo verified — it matches your description"
              : "Photo attached, but it didn't clearly match the description"}
          </p>
        )}
      </section>

      <section className="panel p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-muted">
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

      <div className="flex flex-col gap-3 sm:flex-row">
        <Link href={`/track/${complaint.id}`} className="btn btn-primary px-6">
          Track this report
        </Link>
        <button onClick={onReportAnother} className="btn btn-secondary px-6">
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
      <dt className="text-[11px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className={`mt-0.5 font-medium ${accent ?? "text-ink"}`}>{value}</dd>
    </div>
  );
}
