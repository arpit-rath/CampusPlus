/**
 * Connection state for the realtime feed.
 *
 * Worth its own component because the honest version matters: a dashboard
 * that claims "Live" while its socket is dead is worse than one that admits
 * it is reconnecting, since everything on screen is then quietly stale.
 */

export type ConnectionStatus = "connecting" | "live" | "offline";

const STYLES: Record<ConnectionStatus, { label: string; dot: string; text: string }> = {
  connecting: { label: "Connecting", dot: "bg-ink/40", text: "text-ink/45" },
  live: { label: "Live", dot: "bg-calm animate-pulse", text: "text-calm" },
  offline: { label: "Reconnecting", dot: "bg-critical", text: "text-critical" },
};

export function LiveIndicator({ status }: { status: ConnectionStatus }) {
  const style = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest ${style.text}`}
      title={
        status === "live"
          ? "Connected to the API's websocket feed — updates arrive as they happen."
          : "Not connected; the view may be stale until the socket reconnects."
      }
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}
