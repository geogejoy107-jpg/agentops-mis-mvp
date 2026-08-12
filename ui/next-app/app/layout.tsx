import type { Metadata } from "next";
import "../src/styles/globals.css";

export const metadata: Metadata = {
  title: "AgentOps MIS",
  description: "AgentOps MIS production control plane.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
