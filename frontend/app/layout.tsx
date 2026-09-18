import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Switchboard · Internal change workflow",
  description: "Investigate customer requests and review internal endpoint-change proposals.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
