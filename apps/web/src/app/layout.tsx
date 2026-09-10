import type { Metadata, Viewport } from "next";
import { Fira_Code, Fira_Sans } from "next/font/google";
import "./globals.css";

// Self-hosted by next/font at build time: no render-blocking request to
// Google, no layout shift from a late swap. Fira Sans / Fira Code is the
// pairing the design search returned for a data-dense operations product.
const firaSans = Fira_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-fira-sans",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fira-code",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CampusPlus",
  description:
    "AI-powered campus problem intelligence. Finds which reports are the same problem, which keep coming back, and which deserve attention first.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // No maximum-scale / user-scalable=no: blocking pinch zoom is an
  // accessibility failure, not a polish detail.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#EFF1EE" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0F14" },
  ],
};

/**
 * Runs before first paint to stamp the saved theme onto <html>.
 *
 * This has to be a blocking inline script. A React effect runs *after* the
 * first paint, which is precisely when a light-flash-then-dark would be
 * visible to someone who chose dark. Wrapped in try/catch because
 * localStorage throws outright in some privacy modes, and a theme
 * preference is never worth breaking the page over.
 */
const THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("campusplus.theme");
    if (stored === "light" || stored === "dark") {
      document.documentElement.setAttribute("data-theme", stored);
    }
  } catch (e) {}
  // Opts the document in to the hidden-then-revealed entrance state. Only
  // set when scripting is actually running, so a failed bundle leaves the
  // content visible rather than blank.
  document.documentElement.classList.add("js-reveal");
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body
        className={`${firaSans.variable} ${firaCode.variable} min-h-screen font-sans antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
