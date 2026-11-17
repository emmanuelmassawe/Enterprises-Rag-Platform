"use client";

import { getWebInstrumentations, initializeFaro } from "@grafana/faro-web-sdk";
import { useEffect, type ReactNode } from "react";

export function FaroProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_FARO_COLLECTOR_URL;
    if (!url || window.__sagefieldFaroInitialized) return;
    initializeFaro({ url, app: { name: "sagefield-web", version: process.env.NEXT_PUBLIC_RELEASE_VERSION ?? "unknown" }, instrumentations: getWebInstrumentations({ captureConsole: false }), beforeSend: (event) => event.type === "log" ? null : event });
    window.__sagefieldFaroInitialized = true;
  }, []);
  return children;
}
