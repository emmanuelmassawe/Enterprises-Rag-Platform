"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { FilePlus2, FileText, FolderPlus, LoaderCircle, RefreshCw, Search, Trash2, UploadCloud, X } from "lucide-react";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { apiFetch, idempotencyKey, type Collection, type Page } from "@/lib/api";

type DocumentRow = { id: string; collection_id: string; filename: string; size_bytes: number; status: string; page_count: number | null; created_at: string; job_id: string | null; progress: number; stage: string; retryable: boolean; error_code: string | null };
type UploadRow = { key: string; filename: string; progress: number; status: "uploading" | "queued" | "failed"; error?: string; jobId?: string; retryable?: boolean; file?: File };

export function KnowledgePanel({ canEdit }: { canEdit: boolean }) {
  const t = useTranslations("common");
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedCollection, setSelectedCollection] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [uploadRows, setUploadRows] = useState<UploadRow[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [description, setDescription] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DocumentRow | null>(null);
  const [feedback, setFeedback] = useState("");
  const collections = useQuery({ queryKey: ["collections"], queryFn: () => apiFetch<Page<Collection>>("collections?limit=100") });
  const documents = useQuery({
    queryKey: ["documents", selectedCollection, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "100" });
      if (selectedCollection) params.set("collection_id", selectedCollection);
      if (statusFilter) params.set("status", statusFilter);
      return apiFetch<Page<DocumentRow>>(`documents?${params}`);
    },
    refetchInterval: (query) => query.state.data?.items.some((item) => ["queued", "processing", "deleting"].includes(item.status)) ? 5_000 : false,
  });
  const createMutation = useMutation({
    mutationFn: () => apiFetch<Collection>("collections", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: collectionName.trim(), description: description.trim() || null }) }),
    onSuccess: async (collection) => { setCollectionName(""); setDescription(""); setCreateOpen(false); setSelectedCollection(collection.id); await queryClient.invalidateQueries({ queryKey: ["collections"] }); },
    onError: (error) => setFeedback(error instanceof Error ? error.message : "Collection could not be created."),
  });
  const deleteMutation = useMutation({
    mutationFn: (document: DocumentRow) => apiFetch(`documents/${document.id}`, { method: "DELETE" }),
    onSuccess: async () => { setDeleteTarget(null); setFeedback("Deletion was accepted. The document and its derived data are being removed."); await queryClient.invalidateQueries({ queryKey: ["documents"] }); },
    onError: (error) => setFeedback(error instanceof Error ? error.message : "Document could not be deleted."),
  });

  function uploadOne(file: File) {
    if (!canEdit) return;
    const key = crypto.randomUUID();
    if (file.type !== "application/pdf" || !file.name.toLowerCase().endsWith(".pdf")) {
      setUploadRows((rows) => [{ key, filename: file.name, progress: 0, status: "failed", error: "Only PDF files are supported.", file }, ...rows]); return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setUploadRows((rows) => [{ key, filename: file.name, progress: 0, status: "failed", error: "This file exceeds the 100 MB upload limit.", file }, ...rows]); return;
    }
    if (!selectedCollection) {
      setUploadRows((rows) => [{ key, filename: file.name, progress: 0, status: "failed", error: "Choose a collection before uploading.", file }, ...rows]); return;
    }
    setUploadRows((rows) => [{ key, filename: file.name, progress: 0, status: "uploading", file }, ...rows]);
    const payload = new FormData(); payload.set("file", file); payload.set("collection_id", selectedCollection);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/rag/v1/documents");
    xhr.setRequestHeader("Idempotency-Key", idempotencyKey());
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) setUploadRows((rows) => rows.map((row) => row.key === key ? { ...row, progress: Math.round((event.loaded / event.total) * 100) } : row));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const data: unknown = JSON.parse(xhr.responseText);
        const job = typeof data === "object" && data !== null && "job" in data ? (data as { job: { id?: string } }).job : {};
        setUploadRows((rows) => rows.map((row) => row.key === key ? { ...row, progress: 100, status: "queued", jobId: job.id } : row));
        void queryClient.invalidateQueries({ queryKey: ["documents"] });
      } else {
        let detail = "Upload was rejected.";
        try { const problem = JSON.parse(xhr.responseText) as { detail?: string }; detail = problem.detail ?? detail; } catch { /* The response may be empty. */ }
        setUploadRows((rows) => rows.map((row) => row.key === key ? { ...row, status: "failed", error: detail, file } : row));
      }
    };
    xhr.onerror = () => setUploadRows((rows) => rows.map((row) => row.key === key ? { ...row, status: "failed", error: "Network error. Try uploading the file again.", file } : row));
    xhr.send(payload);
  }

  function onFiles(event: ChangeEvent<HTMLInputElement>) {
    for (const file of Array.from(event.target.files ?? [])) uploadOne(file);
    event.target.value = "";
  }
  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setDragActive(false);
    for (const file of Array.from(event.dataTransfer.files)) uploadOne(file);
  }
  async function retryUpload(row: UploadRow) {
    if (!row.jobId) return;
    try {
      await apiFetch(`jobs/${row.jobId}/retry`, { method: "POST", headers: { "idempotency-key": idempotencyKey() } });
      setUploadRows((rows) => rows.map((item) => item.key === row.key ? { ...item, status: "queued", error: undefined } : item));
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    } catch (error) { setFeedback(error instanceof Error ? error.message : "The failed job could not be retried."); }
  }

  const items = documents.data?.items ?? [];
  const filtered = items.filter((item) => item.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="mx-auto max-w-[1450px] space-y-5">
      <section className="relative overflow-hidden rounded-[1.5rem] bg-[#173e31] p-6 text-[#f5f5eb] sm:p-9">
        <div className="absolute -right-8 -top-28 h-80 w-80 rounded-full border border-white/10" /><div className="absolute -right-4 -top-24 h-64 w-64 rounded-full border border-white/10" />
        <div className="relative flex flex-wrap items-end justify-between gap-5"><div className="max-w-xl"><p className="text-[11px] font-semibold uppercase tracking-[.2em] text-[#bdd5c3]">A considered source library</p><h2 className="mt-3 text-3xl font-medium tracking-[-.04em] sm:text-4xl">Keep useful knowledge close.</h2><p className="mt-3 text-sm leading-6 text-[#d1ded5]">Organize approved documents into collections. Uploads are indexed in the background and remain unavailable to answers until ready.</p></div>{canEdit && <button className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#e5c995] px-4 font-semibold text-[#2d3b31] hover:bg-[#f0d9ac]" onClick={() => setCreateOpen(true)}><FolderPlus size={17} />{t("createCollection")}</button>}</div>
      </section>
      <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="surface overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-6"><div><h3 className="text-base font-semibold">{t("documents")}</h3><p className="mt-1 text-xs text-muted">Search, filter and review ingestion state.</p></div><span className="rounded-full bg-brand-tint px-3 py-1 text-xs font-semibold text-brand">{items.length} items</span></div>
          <div className="flex flex-wrap gap-2 border-b border-line px-5 py-4 sm:px-6"><div className="relative min-w-[180px] flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={15} /><input className="field min-h-10 pl-9 text-sm" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("search")} aria-label={t("search")} /></div><select className="field !min-h-10 !w-auto min-w-40 text-sm" value={selectedCollection} onChange={(event) => setSelectedCollection(event.target.value)} aria-label={t("collection")}><option value="">All collections</option>{collections.data?.items.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select><select className="field !min-h-10 !w-auto min-w-32 text-sm" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label={t("status")}><option value="">All status</option><option value="queued">{t("queued")}</option><option value="processing">{t("processing")}</option><option value="ready">{t("ready")}</option><option value="failed">{t("failed")}</option></select></div>
          <div className="divide-y divide-line">
            {filtered.map((document) => <article key={document.id} className="flex flex-wrap items-center gap-3 px-5 py-4 sm:px-6"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#f3eee4] text-[#8f7551] dark:bg-[#322c22]"><FileText size={18} /></span><div className="min-w-0 flex-1"><h4 className="truncate text-sm font-semibold">{document.filename}</h4><p className="mt-1 truncate text-xs text-muted">{collections.data?.items.find((item) => item.id === document.collection_id)?.name ?? "Collection"} · {formatBytes(document.size_bytes)}{document.page_count ? ` · ${document.page_count} pages` : ""}</p></div><div className="min-w-28 text-right"><StatusPill status={document.status} t={t} /><p className="mt-1 text-[10px] text-muted">{document.status === "processing" ? `${document.progress}% · ${document.stage ?? "processing"}` : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(document.created_at))}</p></div>{canEdit && <div className="flex gap-1">{document.status === "failed" && document.retryable && document.job_id && <button className="icon-button" aria-label={t("retry")} title={t("retry")} onClick={() => void retryUpload({ key: document.id, filename: document.filename, progress: 0, status: "failed", jobId: document.job_id!, retryable: true })}><RefreshCw size={16} /></button>}<button className="icon-button" aria-label={t("delete")} title={t("delete")} onClick={() => setDeleteTarget(document)}><Trash2 size={16} /></button></div>}</article>)}
            {documents.isPending && <div className="p-8 text-center text-sm text-muted"><LoaderCircle className="mx-auto mb-2 animate-spin" size={20} />{t("loading")}</div>}
            {!documents.isPending && filtered.length === 0 && <div className="p-10 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-panel-soft text-muted"><FileText size={20} /></span><p className="mt-3 text-sm font-semibold">{t("noDocuments")}</p><p className="mt-1 text-xs text-muted">Choose a collection, then add a PDF to begin.</p></div>}
          </div>
        </div>
        <aside className="space-y-4">
          {canEdit ? <div className={`surface p-5 transition-colors ${dragActive ? "border-brand bg-brand-tint" : ""}`} onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragActive(false)} onDrop={onDrop}>
            <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-tint text-brand"><UploadCloud size={19} /></span><div><h3 className="text-sm font-semibold">{t("upload")}</h3><p className="mt-0.5 text-xs text-muted">{t("uploadHelp")}</p></div></div>
            <label className="mt-4 block text-xs font-medium text-muted">{t("collection")}<select className="field mt-1.5 text-sm" value={selectedCollection} onChange={(event) => setSelectedCollection(event.target.value)}><option value="">Select a collection</option>{collections.data?.items.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select></label>
            <button className="mt-4 flex min-h-32 w-full flex-col items-center justify-center rounded-xl border border-dashed border-line bg-panel-soft px-4 text-center transition-colors hover:border-brand" onClick={() => inputRef.current?.click()} onKeyDown={(event) => { if (event.key === "Enter") inputRef.current?.click(); }}><FilePlus2 size={22} className="text-brand" /><span className="mt-2 text-sm font-semibold">{t("drop")}</span><span className="mt-1 text-[11px] text-muted">Your administrator&apos;s upload limit is enforced by the server.</span></button>
            <input ref={inputRef} className="sr-only" type="file" accept="application/pdf,.pdf" multiple onChange={onFiles} aria-label={t("upload")} />
            <p className="mt-3 text-[11px] leading-5 text-muted">PDFs are uploaded directly through the same-origin server. Files stay private to your tenant.</p>
          </div> : <div className="surface p-5"><h3 className="text-sm font-semibold">Read-only access</h3><p className="mt-2 text-xs leading-5 text-muted">Your role can browse documents. An editor can add or remove files.</p></div>}
          {uploadRows.length > 0 && <div className="surface p-5"><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Upload activity</h3><button className="icon-button !min-h-8 !min-w-8" onClick={() => setUploadRows([])} aria-label="Clear upload activity"><X size={15} /></button></div><div className="mt-3 space-y-3">{uploadRows.map((row) => <div key={row.key} className="rounded-xl bg-panel-soft p-3"><div className="flex items-start gap-2"><FileText size={15} className="mt-0.5 shrink-0 text-muted" /><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{row.filename}</p><p className="mt-1 text-[11px] text-muted">{row.status === "uploading" ? `Uploading ${row.progress}%` : row.status === "queued" ? t("queued") : row.error}</p></div>{row.status === "failed" && row.file && <button className="icon-button !min-h-8 !min-w-8" aria-label={t("retry")} onClick={() => uploadOne(row.file!)}><RefreshCw size={14} /></button>}</div>{row.status === "uploading" && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-brand transition-all" style={{ width: `${row.progress}%` }} /></div>}</div>)}</div></div>}
        </aside>
      </section>
      {feedback && <p role="status" className="fixed bottom-5 left-1/2 z-30 -translate-x-1/2 rounded-xl bg-ink px-4 py-3 text-sm text-panel shadow-xl">{feedback}<button className="ml-3" onClick={() => setFeedback("")} aria-label={t("cancel")}><X className="inline" size={14} /></button></p>}
      <Dialog.Root open={createOpen} onOpenChange={setCreateOpen}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-panel p-6 shadow-2xl"><Dialog.Title className="text-lg font-semibold">{t("createCollection")}</Dialog.Title><p className="mt-1 text-sm text-muted">Keep related documents together for focused answers.</p><form onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }} className="mt-5 space-y-4"><label className="block text-xs font-semibold">Collection name<input className="field mt-1.5" required maxLength={120} value={collectionName} onChange={(event) => setCollectionName(event.target.value)} /></label><label className="block text-xs font-semibold">Description <span className="font-normal text-muted">optional</span><textarea className="field mt-1.5" maxLength={1000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label><div className="flex justify-end gap-2"><Dialog.Close className="secondary-button">{t("cancel")}</Dialog.Close><button className="primary-button" disabled={createMutation.isPending}><FolderPlus size={16} />{t("createCollection")}</button></div></form></Dialog.Content></Dialog.Portal></Dialog.Root>
      <Dialog.Root open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-panel p-6 shadow-2xl"><Dialog.Title className="text-lg font-semibold">Delete this document?</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted">{deleteTarget?.filename} and its derived content will be removed. The operation may take a short time to finish.</Dialog.Description><div className="mt-5 flex justify-end gap-2"><Dialog.Close className="secondary-button">{t("cancel")}</Dialog.Close><button className="rounded-xl bg-red-700 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)} disabled={deleteMutation.isPending}>{deleteMutation.isPending ? t("loading") : t("delete")}</button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
    </div>
  );
}

function StatusPill({ status, t }: { status: string; t: ReturnType<typeof useTranslations> }) {
  const tone = status === "ready" ? "bg-[#e3f1e9] text-[#236b53] dark:bg-[#213d30] dark:text-[#a6e1c2]" : status === "failed" ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200" : status === "processing" ? "bg-[#f3eee4] text-[#7d633a] dark:bg-[#322c22] dark:text-[#e0bd7d]" : "bg-panel-soft text-muted";
  const label = ["queued", "processing", "ready", "failed"].includes(status) ? t(status as "queued" | "processing" | "ready" | "failed") : status;
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold ${tone}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</span>;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
