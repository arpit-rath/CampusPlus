import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-start justify-center gap-6 px-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-ink/50">
          CampusPluse
        </p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight">
          AI-powered campus problem intelligence
        </h1>
        <p className="mt-3 max-w-md text-ink/70">
          Report a campus issue, or open the admin console to see what's
          trending, recurring, and overdue.
        </p>
      </div>
      <div className="flex gap-3">
        <Link
          href="/report"
          className="rounded-md bg-signal px-4 py-2 font-medium text-white"
        >
          Report a problem
        </Link>
        <Link
          href="/dashboard"
          className="rounded-md border border-ink/20 px-4 py-2 font-medium"
        >
          Admin console
        </Link>
      </div>
    </main>
  );
}
