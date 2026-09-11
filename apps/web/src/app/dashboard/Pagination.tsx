"use client";

/**
 * Page-size control and numbered pager for the complaint queue.
 *
 * The queue is sorted by priority, so the first page is the part that always
 * matters and the tail is the part an operator visits deliberately. That is
 * exactly the shape search-results pagination is built for: a definite page
 * size, a visible total, and numbered pages you can jump between — rather
 * than infinite scroll, which hides the total and makes "the thing I saw
 * yesterday near the bottom" unreachable.
 *
 * Paging is done in the browser on purpose. The dashboard already holds the
 * whole filtered list because the map, the recurring panel and Ask CampusPlus
 * all read from it; asking the API for one page at a time would mean either
 * fetching twice or leaving those panels with a partial view of the campus.
 * The list endpoint caps at 500 rows, so the array being sliced is bounded.
 */

const PAGE_SIZES = [10, 25, 50] as const;

/**
 * Which page numbers to draw: always the first and last, the current page
 * with a neighbour either side, and an ellipsis wherever that skips a run.
 */
export function pageWindow(current: number, total: number): (number | "gap")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages = new Set([1, total, current, current - 1, current + 1]);
  if (current <= 3) [2, 3, 4].forEach((p) => pages.add(p));
  if (current >= total - 2) [total - 3, total - 2, total - 1].forEach((p) => pages.add(p));

  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);

  const out: (number | "gap")[] = [];
  let previous = 0;
  for (const page of sorted) {
    if (previous && page - previous > 1) out.push("gap");
    out.push(page);
    previous = page;
  }
  return out;
}

export function Pagination({
  total,
  page,
  pageSize,
  onPage,
  onPageSize,
}: {
  total: number;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  const stepClass = "btn btn-secondary btn-sm";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink/10 px-4 py-3">
      <div className="flex items-center gap-2">
        <label htmlFor="page-size" className="text-xs text-muted">
          Show
        </label>
        <select
          id="page-size"
          value={pageSize}
          onChange={(e) => onPageSize(Number(e.target.value))}
          className="input input-sm w-auto"
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size} per page
            </option>
          ))}
        </select>
        <p className="text-xs text-muted" aria-live="polite">
          {total === 0 ? "Nothing to show" : `${first}–${last} of ${total}`}
        </p>
      </div>

      {pageCount > 1 && (
        <nav aria-label="Complaint queue pages" className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onPage(page - 1)}
            disabled={page === 1}
            className={stepClass}
          >
            Previous
          </button>

          {pageWindow(page, pageCount).map((entry, i) =>
            entry === "gap" ? (
              <span
                key={`gap-${i}`}
                aria-hidden="true"
                className="px-1 text-xs text-muted"
              >
                …
              </span>
            ) : (
              <button
                key={entry}
                type="button"
                onClick={() => onPage(entry)}
                aria-current={entry === page ? "page" : undefined}
                aria-label={`Page ${entry}`}
                className={`inline-flex h-9 min-w-[36px] cursor-pointer items-center justify-center rounded-md px-2 font-mono text-xs tabular-nums transition-colors duration-200 ${
                  entry === page
                    ? "bg-ink font-bold text-paper"
                    : "text-ink/80 hover:bg-ink/5 hover:text-ink"
                }`}
              >
                {entry}
              </button>
            ),
          )}

          <button
            type="button"
            onClick={() => onPage(page + 1)}
            disabled={page === pageCount}
            className={stepClass}
          >
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
