import type { Metadata } from "next";

import { AppProvider } from "@/components/app-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "ComplaintGuard",
  description: "Bilingual financial complaint routing and analytics MVP",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
