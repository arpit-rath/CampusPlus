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
