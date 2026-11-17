"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";
import { FaroProvider } from "./telemetry/faro-provider";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false } } }));
  return <QueryClientProvider client={client}><ThemeProvider attribute="class" defaultTheme="system" enableSystem><FaroProvider>{children}</FaroProvider></ThemeProvider></QueryClientProvider>;
}
