"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Activity, Check, CircleAlert, Copy, KeyRound, LoaderCircle, LockKeyhole, RefreshCw, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { apiFetch, idempotencyKey, type Page } from "@/lib/api";

type QuarantineItem = { chunk_id: string; document_id: string; page: number | null; reason_codes: string[]; created_at: string; plain_text: string };
type ApiKey = { id: string; name: string; scopes: string[]; created_at: string; expires_at: string | null; last_used_at: string | null; revoked: boolean };
type Usage = { query_count: number; input_tokens: number; output_tokens: number; estimated_cost_usd: number | null; cost_note: string };
type ServiceStatus = { status: string; checks: Record<string, string> };
type Section = "quarantine" | "usage" | "keys" | "status";

export function AdminPanel() {
  const t = useTranslations("common");
  const client = useQueryClient();
  const [section, setSection] = useState<Section>("quarantine");
  const [decisionReason, setDecisionReason] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [keyName, setKeyName] = useState("");
  const [keyScope, setKeyScope] = useState("read");
  const [createdSecret, setCreatedSecret] = useState("");
  const [keyDialogOpen, setKeyDialogOpen] = useState(false);
  const quarantine = useQuery({ queryKey: ["quarantine"], queryFn: () => apiFetch<Page<QuarantineItem>>("admin/quarantine?limit=50"), refetchInterval: 30_000 });
  const usage = useQuery({ queryKey: ["usage"], queryFn: () => {
    const until = new Date(); const since = new Date(until.getTime() - 30 * 86_400_000);
    return apiFetch<Usage>(`admin/usage?since=${encodeURIComponent(since.toISOString())}&until=${encodeURIComponent(until.toISOString())}`);
  }, enabled: section === "usage" });
  const status = useQuery({ queryKey: ["service-status"], queryFn: () => apiFetch<ServiceStatus>("admin/status"), enabled: section === "status", refetchInterval: 30_000 });
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: () => apiFetch<Page<ApiKey>>("admin/api-keys?limit=100"), enabled: section === "keys" });
  const decide = useMutation({
    mutationFn: ({ item, decision }: { item: QuarantineItem; decision: "approve" | "reject" }) => apiFetch(`admin/quarantine/${item.chunk_id}/decision`, { method: "POST", headers: { "content-type": "application/json", "idempotency-key": idempotencyKey() }, body: JSON.stringify({ decision, reason: decisionReason[item.chunk_id]?.trim() || (decision === "approve" ? "Reviewed by tenant administrator." : "Rejected by tenant administrator.") }) }),
    onSuccess: async () => { setMessage("Review decision recorded and audited."); await client.invalidateQueries({ queryKey: ["quarantine"] }); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Decision could not be saved."),
  });
  const createKey = useMutation({
    mutationFn: () => apiFetch<{ key: ApiKey; secret: string }>("admin/api-keys", { method: "POST", headers: { "content-type": "application/json", "idempotency-key": idempotencyKey() }, body: JSON.stringify({ name: keyName.trim(), scopes: [keyScope] }) }),
    onSuccess: async (result) => { setCreatedSecret(result.secret); setKeyName(""); setKeyDialogOpen(true); await client.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Credential could not be issued."),
  });
  const revokeKey = useMutation({
    mutationFn: (id: string) => apiFetch<void>(`admin/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: async () => { setMessage("Credential revoked."); await client.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Credential could not be revoked."),
  });

  const tabs: { key: Section; label: string; icon: typeof ShieldCheck }[] = [
    { key: "quarantine", label: t("adminQueue"), icon: ShieldCheck },
    { key: "usage", label: t("usage"), icon: Activity },
    { key: "keys", label: "API keys", icon: KeyRound },
    { key: "status", label: t("serviceStatus"), icon: CircleAlert },
  ];

  return (
    <div className="mx-auto max-w-[1380px] space-y-5">
      <section className="surface flex flex-wrap items-end justify-between gap-5 p-6 sm:p-8"><div className="max-w-2xl"><p className="text-xs font-semibold uppercase tracking-[.17em] text-brand">Tenant controls</p><h2 className="mt-2 text-3xl font-semibold tracking-[-.04em]">{t("admin")}</h2><p className="mt-2 text-sm leading-6 text-muted">Review flagged content, manage credentials, and check workspace activity. Every action is tenant-scoped and recorded.</p></div><span className="inline-flex items-center gap-2 rounded-full bg-brand-tint px-3 py-1.5 text-xs font-semibold text-brand"><LockKeyhole size={14} />Admin access active</span></section>
      <section className="surface overflow-hidden">
        <div className="flex gap-1 overflow-x-auto border-b border-line px-3 pt-3 sm:px-5" role="tablist" aria-label="Administrative sections">{tabs.map(({ key, label, icon: Icon }) => <button role="tab" aria-selected={section === key} key={key} onClick={() => setSection(key)} className={`inline-flex min-h-11 shrink-0 items-center gap-2 rounded-t-xl px-4 text-sm font-medium ${section === key ? "border-b-2 border-brand text-brand" : "text-muted hover:bg-panel-soft hover:text-ink"}`}><Icon size={16} />{label}</button>)}</div>
        {section === "quarantine" && <div className="divide-y divide-line">{quarantine.isPending ? <Loading label={t("loading")} /> : quarantine.data?.items.length ? quarantine.data.items.map((item) => <article key={item.chunk_id} className="grid gap-5 p-5 sm:p-6 xl:grid-cols-[minmax(0,1fr)_280px]"><div><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#f3eee4] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-[#7d633a] dark:bg-[#322c22] dark:text-[#e0bd7d]">Pending review</span><span className="text-xs text-muted">{item.page ? `Page ${item.page}` : "Page unavailable"} · {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(item.created_at))}</span></div><p className="mt-3 text-[11px] text-muted">Document {item.document_id}</p><div className="mt-3 max-h-48 overflow-y-auto rounded-xl bg-panel-soft p-4 text-sm leading-6">{item.plain_text}</div><div className="mt-3 flex flex-wrap gap-1.5">{item.reason_codes.map((reason) => <span key={reason} className="rounded-full border border-line px-2.5 py-1 text-[10px] font-medium text-muted">{reason}</span>)}</div></div><div className="flex flex-col justify-center gap-2"><label className="text-xs font-semibold">Review note <span className="font-normal text-muted">optional</span><textarea className="field mt-1.5 text-sm" rows={3} maxLength={1000} value={decisionReason[item.chunk_id] ?? ""} onChange={(event) => setDecisionReason((current) => ({ ...current, [item.chunk_id]: event.target.value }))} placeholder="Record why you made this decision" /></label><div className="grid grid-cols-2 gap-2"><button className="secondary-button !min-h-10 text-xs" onClick={() => decide.mutate({ item, decision: "reject" })} disabled={decide.isPending}><X size={14} />{t("reject")}</button><button className="primary-button !min-h-10 text-xs" onClick={() => decide.mutate({ item, decision: "approve" })} disabled={decide.isPending}><Check size={14} />{t("approve")}</button></div></div></article>) : <Empty label="No documents are waiting for quarantine review." />}</div>}
        {section === "usage" && <div className="p-5 sm:p-7">{usage.isPending ? <Loading label={t("loading")} /> : usage.data ? <><div className="grid gap-3 sm:grid-cols-3"><Metric label="Queries · last 30 days" value={usage.data.query_count.toLocaleString()} /><Metric label="Input tokens" value={usage.data.input_tokens.toLocaleString()} /><Metric label="Output tokens" value={usage.data.output_tokens.toLocaleString()} /></div><div className="mt-4 rounded-xl border border-line bg-panel-soft p-4"><p className="text-sm font-semibold">Estimated provider spend</p><p className="mt-1 text-sm text-muted">{usage.data.estimated_cost_usd === null ? usage.data.cost_note : `$${usage.data.estimated_cost_usd.toFixed(2)}`}</p><p className="mt-2 text-xs leading-5 text-muted">Token totals come from tenant query records. Costs are not calculated until model pricing is configured.</p></div></> : <Empty label="Usage could not be loaded." />}</div>}
        {section === "status" && <div className="p-5 sm:p-7"><div className="mb-4 flex items-center justify-between"><div><h3 className="font-semibold">{t("serviceStatus")}</h3><p className="mt-1 text-xs text-muted">Tenant-safe dependency readiness. Refreshes every 30 seconds.</p></div><button className="icon-button" onClick={() => void status.refetch()} aria-label={t("retry")}><RefreshCw size={16} /></button></div>{status.isPending ? <Loading label={t("loading")} /> : <><div className={`mb-4 rounded-xl p-4 text-sm font-semibold ${status.data?.status === "ready" ? "bg-brand-tint text-brand" : "bg-[#fbf1df] text-[#715426] dark:bg-[#332b1d] dark:text-[#e0bd7d]"}`}>Workspace status: {status.data?.status ?? "unknown"}</div><div className="grid gap-2 sm:grid-cols-2">{Object.entries(status.data?.checks ?? {}).map(([name, state]) => <div key={name} className="flex min-h-14 items-center justify-between rounded-xl border border-line px-4"><span className="text-sm capitalize">{name.replaceAll("_", " ")}</span><span className="inline-flex items-center gap-2 text-xs font-semibold"><span className={`h-2 w-2 rounded-full ${state === "ok" ? "bg-[#4d9268]" : "bg-[#c28e3f]"}`} />{state.replaceAll("_", " ")}</span></div>)}</div></>}</div>}
        {section === "keys" && <div className="p-5 sm:p-7"><div className="flex flex-wrap items-end justify-between gap-4"><div><h3 className="font-semibold">API credentials</h3><p className="mt-1 text-xs leading-5 text-muted">Secrets are shown once. For web sign-in, a credential must also be mapped to an approved email in the protected server environment.</p></div><Dialog.Root open={keyDialogOpen} onOpenChange={(open) => { setKeyDialogOpen(open); if (!open) setCreatedSecret(""); }}><Dialog.Trigger asChild><button className="primary-button" onClick={() => { setCreatedSecret(""); setKeyDialogOpen(true); }}><KeyRound size={16} />Create key</button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-panel p-6 shadow-2xl"><Dialog.Title className="text-lg font-semibold">{createdSecret ? "Copy this secret now" : "Create an API key"}</Dialog.Title>{createdSecret ? <><p className="mt-2 text-sm leading-6 text-muted">This credential will not be shown again. Save it in the approved secret manager, never in a source file or browser storage.</p><code className="mt-4 block break-all rounded-xl bg-panel-soft p-4 text-xs">{createdSecret}</code><button className="secondary-button mt-3" onClick={() => void navigator.clipboard.writeText(createdSecret)}><Copy size={14} />Copy secret</button><Dialog.Close className="primary-button mt-5 w-full justify-center">Done</Dialog.Close></> : <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); createKey.mutate(); }}><label className="block text-xs font-semibold">Name<input className="field mt-1.5" value={keyName} onChange={(event) => setKeyName(event.target.value)} maxLength={120} required /></label><label className="block text-xs font-semibold">Access level<select className="field mt-1.5" value={keyScope} onChange={(event) => setKeyScope(event.target.value)}><option value="read">Viewer · read</option><option value="write">Editor · read and write</option><option value="admin">Admin · all tenant actions</option></select></label><div className="flex justify-end gap-2"><Dialog.Close className="secondary-button">{t("cancel")}</Dialog.Close><button className="primary-button" disabled={createKey.isPending}>Create key</button></div></form>}</Dialog.Content></Dialog.Portal></Dialog.Root></div>
          <div className="mt-5 divide-y divide-line rounded-xl border border-line">{keys.isPending ? <Loading label={t("loading")} /> : (keys.data?.items ?? []).map((key) => <div key={key.id} className="flex flex-wrap items-center gap-3 px-4 py-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-panel-soft text-muted"><KeyRound size={16} /></span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{key.name}</p><p className="mt-1 text-xs text-muted">{key.scopes.join(" · ")} · created {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(key.created_at))}</p></div>{key.revoked ? <span className="rounded-full bg-red-50 px-2.5 py-1 text-[10px] text-red-800 dark:bg-red-950/40 dark:text-red-200">Revoked</span> : <button className="secondary-button !min-h-9 !px-3 text-xs" onClick={() => revokeKey.mutate(key.id)}><X size={13} />Revoke</button>}</div>)}{keys.data?.items.length === 0 && <Empty label="No API credentials." />}</div>
        </div>}
      </section>
      {message && <p role="status" className="fixed bottom-5 left-1/2 z-30 -translate-x-1/2 rounded-xl bg-ink px-4 py-3 text-sm text-panel shadow-xl">{message}<button className="ml-3" onClick={() => setMessage("")} aria-label={t("cancel")}><X className="inline" size={14} /></button></p>}
    </div>
  );
}

function Loading({ label }: { label: string }) { return <div className="p-10 text-center text-sm text-muted"><LoaderCircle className="mx-auto mb-2 animate-spin" size={20} />{label}</div>; }
function Empty({ label }: { label: string }) { return <div className="p-10 text-center text-sm text-muted">{label}</div>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-line bg-panel-soft p-4"><p className="text-xs text-muted">{label}</p><p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p></div>; }
