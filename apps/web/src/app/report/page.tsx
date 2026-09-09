"use client";

/**
 * Student complaint report form. Reads any attached photo client-side as a
 * base64 data URL (no upload endpoint needed) and posts straight to
 * `api.createComplaint`. On success we hand off to the live tracker page;
 * on failure we surface an inline message rather than crash, since there's
 * no live backend in this sandbox to exercise the happy path against.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const BUILDINGS = [
  "Block A",
  "Block B",
  "Block C",
  "Library",
  "Hostel Block 1",
  "Hostel Block 2",
  "Cafeteria",
  "Sports Complex",
  "Admin Block",
];

export default function ReportPage() {
  const router = useRouter();

  const [description, setDescription] = useState("");
  const [building, setBuilding] = useState("");
  const [room, setRoom] = useState("");
  const [photoBase64, setPhotoBase64] = useState<string | undefined>(
    undefined,
  );
  const [photoName, setPhotoName] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      setPhotoBase64(undefined);
      setPhotoName(null);
      return;
    }

    setPhotoName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setPhotoBase64(reader.result);
      }
    };
    reader.onerror = () => {
      setError("Couldn't read that photo — try a different file.");
      setPhotoBase64(undefined);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!description.trim()) {
      setError("Describe the problem before submitting.");
      return;
    }
    if (!building) {
      setError("Select a building.");
      return;
    }

    setSubmitting(true);
    try {
      const complaint = await api.createComplaint({
        description: description.trim(),
        location_building: building,
        location_room: room.trim() || undefined,
        photo_base64: photoBase64,
      });
      router.push(`/track/${complaint.id}`);
    } catch {
      setError("Couldn't submit right now — check the API is running.");
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-16">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          CampusPluse · Report
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">
          What&rsquo;s the problem?
        </h1>
        <p className="mt-3 max-w-md text-ink/70">
          Describe the issue, tell us where it is, and add a photo if you
          have one. We&rsquo;ll categorize it, score its priority, and route
          it to the right department automatically.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="description"
            className="text-sm font-medium text-ink"
          >
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            placeholder="e.g. The WiFi has been down in the second-floor common room since this morning."
            className="rounded-md border border-ink/20 bg-white/60 px-3 py-2 text-sm text-ink outline-none focus:border-signal"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="building" className="text-sm font-medium text-ink">
              Building
            </label>
            <select
              id="building"
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              className="rounded-md border border-ink/20 bg-white/60 px-3 py-2 text-sm text-ink outline-none focus:border-signal"
            >
              <option value="">Select a building</option>
              {BUILDINGS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="room" className="text-sm font-medium text-ink">
              Room / area <span className="text-ink/40">(optional)</span>
            </label>
            <input
              id="room"
              type="text"
              value={room}
              onChange={(e) => setRoom(e.target.value)}
              placeholder="e.g. Room 214"
              className="rounded-md border border-ink/20 bg-white/60 px-3 py-2 text-sm text-ink outline-none focus:border-signal"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="photo" className="text-sm font-medium text-ink">
            Photo <span className="text-ink/40">(optional)</span>
          </label>
          <input
            id="photo"
            type="file"
            accept="image/*"
            onChange={handlePhotoChange}
            className="text-sm text-ink/70 file:mr-3 file:rounded-md file:border-0 file:bg-ink/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink"
          />
          {photoName && (
            <p className="text-xs text-ink/50">Attached: {photoName}</p>
          )}
        </div>

        {error && (
          <p className="rounded-md border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-critical">
            {error}
          </p>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-signal px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit report"}
          </button>
        </div>
      </form>
    </main>
  );
}
