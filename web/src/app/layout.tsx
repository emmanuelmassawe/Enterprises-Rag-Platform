import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sagefield | Knowledge workspace", description: "A secure, evidence-led workspace for your organization's knowledge." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><body>{children}</body></html>;
}
