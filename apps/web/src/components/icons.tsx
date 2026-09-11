/**
 * Inline SVG icons.
 *
 * SVG rather than emoji: emoji render differently on every platform, cannot
 * inherit `currentColor`, and are announced literally by screen readers
 * ("sparkles") in the middle of a heading. The skill's style rules list
 * "emoji as icons" as an explicit anti-pattern.
 *
 * All of these are decorative — the adjacent heading carries the meaning —
 * so each is `aria-hidden` and contributes nothing to the accessibility
 * tree. They inherit size from the wrapping element and colour from
 * `currentColor`.
 */

type IconProps = { className?: string };

const base = {
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

export function LayersIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3 3 8l9 5 9-5-9-5Z" />
      <path d="m3 13 9 5 9-5" />
      <path d="m3 18 9 5 9-5" opacity="0.45" />
    </svg>
  );
}

export function BoltIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5Z" />
    </svg>
  );
}

export function ScaleIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3v18" />
      <path d="M5 7h14" />
      <path d="m5 7-3 6a3 3 0 0 0 6 0L5 7Z" />
      <path d="m19 7-3 6a3 3 0 0 0 6 0l-3-6Z" />
      <path d="M8 21h8" />
    </svg>
  );
}

export function ShieldIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function RouteIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="6" cy="19" r="2.5" />
      <circle cx="18" cy="5" r="2.5" />
      <path d="M8.5 19H14a4 4 0 0 0 0-8h-4a4 4 0 0 1 0-8h5.5" />
    </svg>
  );
}

export function ChatIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-6.5A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8Z" />
      <path d="M9 11h6M9 14.5h3.5" opacity="0.6" />
    </svg>
  );
}

export function SparkIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" opacity="0.5" />
      <path d="M12 8.5 13.4 11l2.6 1-2.6 1-1.4 2.5L10.6 13 8 12l2.6-1L12 8.5Z" />
    </svg>
  );
}

/* --- dashboard section icons -------------------------------------------- */

export function GridIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" opacity="0.55" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" opacity="0.55" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

export function RepeatIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 9a5 5 0 0 1 5-5h9" />
      <path d="m15 1 3 3-3 3" />
      <path d="M20 15a5 5 0 0 1-5 5H6" />
      <path d="m9 23-3-3 3-3" />
    </svg>
  );
}

export function MergeIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M6 3v4a5 5 0 0 0 5 5h6" />
      <path d="M6 21v-4a5 5 0 0 1 5-5" />
      <path d="m14 9 3 3-3 3" />
    </svg>
  );
}

export function MapIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" />
      <path d="M9 3v15M15 6v15" opacity="0.5" />
    </svg>
  );
}

export function MailIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="2.5" y="5" width="19" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  );
}

export function ListIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M9 6h12M9 12h12M9 18h12" />
      <path d="M4 6h.01M4 12h.01M4 18h.01" opacity="0.6" />
    </svg>
  );
}

/**
 * The brand mark: three bars, descending — the same shape the priority
 * breakdown draws, rather than a generic abstract glyph. Filled rather than
 * stroked like the rest of this file, so it reads as a mark and not an icon.
 */
export function BrandMark({ className = "h-full w-full" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <rect x="3" y="5" width="18" height="3.4" rx="1.7" />
      <rect x="3" y="10.3" width="12" height="3.4" rx="1.7" opacity="0.7" />
      <rect x="3" y="15.6" width="7" height="3.4" rx="1.7" opacity="0.45" />
    </svg>
  );
}

export function FlagIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 21V4" />
      <path d="M4 4.5h10.5l-1.5 4 1.5 4H4" />
    </svg>
  );
}

export function PanelIcon({ className = "h-full w-full" }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9.5 4v16" />
    </svg>
  );
}
