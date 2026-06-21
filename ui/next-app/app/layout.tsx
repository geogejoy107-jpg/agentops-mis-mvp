import type { Metadata } from "next";
import "../src/styles/globals.css";

export const metadata: Metadata = {
  title: "AgentOps MIS",
  description: "Commercial Next.js parity track for AgentOps MIS.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
