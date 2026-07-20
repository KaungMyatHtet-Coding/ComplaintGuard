import type { Metadata } from "next";
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
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
