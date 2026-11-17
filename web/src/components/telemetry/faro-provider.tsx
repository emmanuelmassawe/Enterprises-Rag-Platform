"use client";

import { getWebInstrumentations, initializeFaro } from "@grafana/faro-web-sdk";
import { useEffect, type ReactNode } from "react";

export function FaroProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (window.__sagefieldFaroInitialized) return;
    void fetch("/api/public-config", { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() as Promise<{ faro_collector_url: string | null; release_version: string }> : null)
      .then((config) => {
        if (!config?.faro_collector_url || window.__sagefieldFaroInitialized) return;
        initializeFaro({ url: config.faro_collector_url, app: { name: "sagefield-web", version: config.release_version }, instrumentations: getWebInstrumentations({ captureConsole: false }), beforeSend: (event) => event.type === "log" ? null : event });
        window.__sagefieldFaroInitialized = true;
      })
      .catch(() => undefined);
  }, []);
  return children;
}
