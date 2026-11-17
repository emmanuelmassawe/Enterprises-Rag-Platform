import type { Metadata } from "next";
import { getLocale } from "next-intl/server";

export const metadata: Metadata = { title: "Sagefield | Knowledge workspace", description: "A secure, evidence-led workspace for your organization's knowledge." };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  return <html lang={locale} suppressHydrationWarning><body>{children}</body></html>;
}
