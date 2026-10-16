import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "ROCmigrator | Migration workspace",
  description: "Follow bounded CUDA-to-HIP repairs and numerical verification in real time.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="en"><body className="bg-background text-foreground antialiased">{children}</body></html>;
}
