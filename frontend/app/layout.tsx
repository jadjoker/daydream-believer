import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Daydream Believer — Day Trader Assistant",
  description: "Real-time market data, technicals, sentiment, options flow, news, and insider activity",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen antialiased overflow-x-hidden">
        {children}
      </body>
    </html>
  );
}
