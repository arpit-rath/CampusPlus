import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CampusPlus",
  description: "AI-powered campus problem intelligence",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
