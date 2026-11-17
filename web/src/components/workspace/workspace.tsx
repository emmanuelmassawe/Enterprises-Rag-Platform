"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { signOut } from "next-auth/react";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Archive, ArrowDown, ArrowLeft, ArrowUp, BookOpenCheck, Check, ChevronDown, CircleHelp, FilePlus2, Files, FolderOpen, Languages, LogOut, Menu, MessageSquareText, Moon, MoreHorizontal, Pin, Plus, Search, Settings2, ShieldCheck, Sparkles, Sun, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { apiFetch, idempotencyKey, type Citation, type Collection, type Conversation, type Message, type Page, streamQuery } from "@/lib/api";
import { KnowledgePanel } from "./knowledge-panel";
import { AdminPanel } from "./admin-panel";

type Identity = { email: string; role: "viewer" | "editor" | "admin" };
type View = "chat" | "knowledge" | "admin" | "settings";
type StreamState = "idle" | "retrieving" | "streaming" | "complete" | "refused" | "error" | "cancelled";
type LocalMessage = Message & { provisional?: boolean; state?: StreamState };

const navigation: { view: View; icon: typeof MessageSquareText; label: string }[] = [
  { view: "chat", icon: MessageSquareText, label: "chat" },
  { view: "knowledge", icon: FolderOpen, label: "knowledge" },
  { view: "admin", icon: ShieldCheck, label: "admin" },
  { view: "settings", icon: Settings2, label: "settings" },
];

export function Workspace({ locale, email, displayName }: { locale: string; email: string; displayName: string }) {
  const t = useTranslations("common");
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { theme, setTheme } = useTheme();
  const [view, setView] = useState<View>("chat");
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [search, setSearch] = useState("");
  const queryBox = useRef<HTMLTextAreaElement>(null);
  const identity = useQuery({ queryKey: ["identity"], queryFn: async () => {
    const response = await fetch("/api/auth/context", { cache: "no-store" });
    if (!response.ok) throw new Error("Workspace identity could not be loaded.");
    return response.json() as Promise<{ email: string; role: Identity["role"] }>;
  } });
  const collections = useQuery({ queryKey: ["collections"], queryFn: () => apiFetch<Page<Collection>>("collections?limit=100") });
  const conversations = useQuery({ queryKey: ["conversations", search], queryFn: () => apiFetch<Page<Conversation>>(`conversations?limit=50${search ? `&search=${encodeURIComponent(search)}` : ""}`) });
  const messages = useQuery({
    queryKey: ["messages", activeConversation],
    enabled: Boolean(activeConversation),
    queryFn: async () => {
      const page = await apiFetch<Page<Message>>(`conversations/${activeConversation}/messages?limit=100`);
      return [...page.items].reverse() as LocalMessage[];
    },
  });
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const isAdmin = identity.data?.role === "admin";
  const isEditor = identity.data?.role === "editor" || isAdmin;
  const localeHref = locale === "en" ? "/sw" : "/en";

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const lastLoadedConversation = useRef<string | null>(null);
  useEffect(() => {
    if (lastLoadedConversation.current !== activeConversation) {
      lastLoadedConversation.current = activeConversation;
      setLocalMessages(messages.data ?? []);
    } else if (messages.data?.length) {
      setLocalMessages(messages.data);
    }
  }, [messages.data, activeConversation]);
  useEffect(() => {
    const refresh = () => void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    window.addEventListener("sagefield:conversations-changed", refresh);
    return () => window.removeEventListener("sagefield:conversations-changed", refresh);
  }, [queryClient]);
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(target.tagName)) {
        event.preventDefault(); queryBox.current?.focus();
      }
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "o") {
        event.preventDefault(); void createConversation();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [identity.data]);
  const title = useMemo(() => navigation.find((item) => item.view === view)?.label ?? "chat", [view]);

  async function createConversation(): Promise<void> {
    const created = await apiFetch<Conversation>("conversations", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "New conversation" }) });
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    setActiveConversation(created.id);
    setLocalMessages([]);
    setView("chat");
  }

  function changeView(next: View) {
    setView(next);
    setMobileMenu(false);
    if (next !== "chat") setCitation(null);
  }

  async function removeConversation(conversationId: string) {
    await apiFetch<void>(`conversations/${conversationId}`, { method: "DELETE" });
    if (activeConversation === conversationId) { setActiveConversation(null); setLocalMessages([]); }
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  async function togglePin(conversation: Conversation) {
    await apiFetch<Conversation>(`conversations/${conversation.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ pinned: !conversation.pinned }) });
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  async function renameConversation(conversation: Conversation) {
    const title = window.prompt(t("rename"), conversation.title);
    if (!title?.trim()) return;
    await apiFetch<Conversation>(`conversations/${conversation.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: title.trim() }) });
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  function changeLocale() {
    const parts = pathname.split("/");
    parts[1] = locale === "en" ? "sw" : "en";
    window.location.assign(parts.join("/") || localeHref);
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <div className="flex min-h-screen">
        <aside className={`${mobileMenu ? "fixed inset-y-0 left-0 z-50 flex w-[284px]" : "hidden"} flex-col border-r border-line bg-panel px-4 py-5 lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-[258px] lg:shrink-0`} aria-label={t("workspace")}>
          <div className="flex items-center justify-between px-2">
            <a href={`/${locale}`} className="flex items-center gap-3 rounded-xl" aria-label={t("product")}><span className="grid h-10 w-10 place-items-center rounded-[14px] bg-brand text-white"><BookOpenCheck size={21} /></span><span className="text-[17px] font-semibold tracking-[-.03em]">Sagefield<span className="ml-1 align-top text-[10px] font-medium text-muted">WORKSPACE</span></span></a>
            <button className="icon-button lg:hidden" onClick={() => setMobileMenu(false)} aria-label={t("cancel")}><X size={19} /></button>
          </div>
          <button className="primary-button mt-8 w-full" onClick={() => void createConversation()}><Plus size={18} />{t("newChat")}</button>
          <nav className="mt-7 space-y-1" aria-label="Main navigation">
            {navigation.filter((item) => item.view !== "admin" || isAdmin).map(({ view: itemView, icon: Icon, label }) => (
              <button key={itemView} onClick={() => changeView(itemView)} className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-medium transition-colors ${view === itemView ? "bg-brand-tint text-brand-strong" : "text-muted hover:bg-panel-soft hover:text-ink"}`} aria-current={view === itemView ? "page" : undefined}>
                <Icon size={18} strokeWidth={1.8} />{t(label)}{itemView === "admin" && <span className="ml-auto rounded-full bg-panel-soft px-2 py-0.5 text-[10px] uppercase tracking-wide">Admin</span>}
              </button>
            ))}
          </nav>
          {view === "chat" && <div className="mt-8 flex min-h-0 flex-1 flex-col">
            <label className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[.16em] text-muted">{t("history")}</label>
            <div className="relative mb-2"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={15} /><input className="field min-h-10 border-transparent bg-panel-soft pl-9 text-sm" placeholder={t("search")} value={search} onChange={(event) => setSearch(event.target.value)} aria-label={t("history")} /></div>
            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
              {(conversations.data?.items ?? []).map((conversation) => <div key={conversation.id} className={`group flex items-center rounded-xl ${activeConversation === conversation.id ? "bg-panel-soft" : "hover:bg-panel-soft"}`}>
                <button className="flex min-h-10 min-w-0 flex-1 items-center gap-2 px-3 text-left text-[13px] text-muted hover:text-ink" onClick={() => { setActiveConversation(conversation.id); setCitation(null); }}><MessageSquareText size={15} className="shrink-0" /><span className="truncate">{conversation.title}</span>{conversation.pinned && <Pin size={12} className="shrink-0 text-gold" />}</button>
                <div className="flex pr-1 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100">
                  <button className="icon-button !min-h-8 !min-w-8" title={conversation.pinned ? t("unpin") : t("pin")} aria-label={conversation.pinned ? t("unpin") : t("pin")} onClick={() => void togglePin(conversation)}><Pin size={13} /></button>
                  <button className="icon-button !min-h-8 !min-w-8" title={t("rename")} aria-label={t("rename")} onClick={() => void renameConversation(conversation)}><MoreHorizontal size={16} /></button>
                  <button className="icon-button !min-h-8 !min-w-8 hover:!text-red-600" title={t("delete")} aria-label={t("delete")} onClick={() => void removeConversation(conversation.id)}><X size={14} /></button>
                </div>
              </div>)}
              {conversations.isPending && <p className="px-3 py-2 text-xs text-muted">{t("loading")}</p>}
            </div>
          </div>}
          <div className="mt-auto border-t border-line pt-4">
            <div className="flex items-center gap-3 rounded-xl px-2 py-2"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#e3ccaa] text-sm font-semibold text-[#4b3928]">{displayName.charAt(0).toUpperCase()}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{displayName}</span><span className="block truncate text-xs text-muted">{identity.data?.role ?? "…"}</span></span><button onClick={() => void signOut({ redirectTo: `/${locale}/login` })} className="icon-button !min-h-9 !min-w-9" aria-label={t("signOut")} title={t("signOut")}><LogOut size={17} /></button></div>
          </div>
        </aside>
        {mobileMenu && <button className="fixed inset-0 z-40 bg-black/35 lg:hidden" aria-label={t("cancel")} onClick={() => setMobileMenu(false)} />}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-line bg-canvas/90 px-4 backdrop-blur-xl sm:px-7">
            <div className="flex items-center gap-3"><button className="icon-button lg:hidden" onClick={() => setMobileMenu(true)} aria-label="Open navigation"><Menu size={20} /></button><div><p className="text-[11px] font-medium uppercase tracking-[.17em] text-muted">{t("workspace")}</p><h1 className="mt-0.5 text-[17px] font-semibold tracking-[-.02em]">{t(title)}</h1></div></div>
            <div className="flex items-center gap-1.5"><button className="icon-button" onClick={changeLocale} aria-label={t("language")} title={t("language")}><Languages size={18} /><span className="ml-1 text-[11px] font-bold uppercase">{locale}</span></button><button className="icon-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={t("theme")} title={t("theme")}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button><button className="icon-button hidden sm:flex" onClick={() => window.dispatchEvent(new Event("sagefield:shortcuts"))} aria-label={t("keyboard")} title={t("keyboard")}><CircleHelp size={18} /></button></div>
          </header>
          <main id="main-content" className="flex-1 p-3 sm:p-5 lg:p-7">
            {view === "chat" && <ChatView t={t} collections={collections.data?.items ?? []} selectedCollections={selectedCollections} setSelectedCollections={setSelectedCollections} conversations={conversations.data?.items ?? []} activeConversation={activeConversation} setActiveConversation={setActiveConversation} messages={localMessages} setMessages={setLocalMessages} queryBox={queryBox} citation={citation} setCitation={setCitation} />}
            {view === "knowledge" && <KnowledgePanel canEdit={isEditor} />}
            {view === "admin" && (isAdmin ? <AdminPanel /> : <section className="surface mx-auto max-w-3xl p-8"><p className="font-semibold">Admin access required</p><p className="mt-2 text-sm text-muted">Your API credential does not grant tenant administrator access.</p></section>)}
            {view === "settings" && <SettingsPanel t={t} email={email} locale={locale} />}
          </main>
          <footer className="flex items-center justify-between px-5 pb-4 text-[11px] text-muted sm:px-8"><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-[#5c9a70]" />Sources remain in your workspace</span><button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => window.dispatchEvent(new Event("sagefield:shortcuts"))}><CircleHelp size={13} />{t("keyboard")}</button></footer>
        </div>
      </div>
    </div>
  );
}

function ChatView({ t, collections, selectedCollections, setSelectedCollections, conversations, activeConversation, setActiveConversation, messages, setMessages, queryBox, citation, setCitation }: {
  t: ReturnType<typeof useTranslations>; collections: Collection[]; selectedCollections: string[]; setSelectedCollections: (ids: string[]) => void; conversations: Conversation[]; activeConversation: string | null; setActiveConversation: (id: string | null) => void; messages: LocalMessage[]; setMessages: React.Dispatch<React.SetStateAction<LocalMessage[]>>; queryBox: React.RefObject<HTMLTextAreaElement | null>; citation: Citation | null; setCitation: (citation: Citation | null) => void;
}) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamStatus, setStreamStatus] = useState<StreamState>("idle");
  const [streamError, setStreamError] = useState("");
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [controller, setController] = useState<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const tRef = useRef(t);
  tRef.current = t;
  const active = conversations.find((conversation) => conversation.id === activeConversation);

  useEffect(() => {
    const handler = () => setShowHelp(true);
    window.addEventListener("sagefield:shortcuts", handler);
    return () => window.removeEventListener("sagefield:shortcuts", handler);
  }, []);
  useEffect(() => {
    if (busy) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  function onComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void sendQuestion(); }
  }

  async function sendQuestion(override?: string) {
    const text = (override ?? question).trim();
    if (!text || busy) return;
    if (selectedCollections.length === 0) { setStreamError(t("allCollections")); return; }
    setQuestion(""); setStreamError(""); setFeedbackSent(null); setBusy(true); setStreamStatus("retrieving");
    let conversationId = activeConversation;
    try {
      if (!conversationId) {
        const created = await apiFetch<Conversation>("conversations", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "New conversation" }) });
        conversationId = created.id; setActiveConversation(created.id);
        window.dispatchEvent(new Event("sagefield:conversations-changed"));
      }
      const userMessage: LocalMessage = { id: crypto.randomUUID(), role: "user", content: text, citations: [], request_id: null, created_at: new Date().toISOString() };
      const assistant: LocalMessage = { id: crypto.randomUUID(), role: "assistant", content: "", citations: [], request_id: null, created_at: new Date().toISOString(), provisional: true, state: "retrieving" };
      setMessages((current) => [...current, userMessage, assistant]);
      const abort = new AbortController(); setController(abort);
      await streamQuery({ question: text, collection_ids: selectedCollections, conversation_id: conversationId, stream: true }, abort.signal, (name, data) => {
        if (name === "retrieval_started") { setStreamStatus("retrieving"); return; }
        if (name === "citations") {
          const items = Array.isArray(data.citations) ? data.citations as Citation[] : [];
          setStreamStatus("streaming");
          setMessages((current) => current.map((item) => item.id === assistant.id ? { ...item, citations: items, state: "streaming" } : item));
          return;
        }
        if (name === "token" && typeof data.text === "string") {
          setMessages((current) => current.map((item) => item.id === assistant.id ? { ...item, content: item.content + data.text, state: "streaming" } : item));
          return;
        }
        if (name === "refusal") {
          const textValue = typeof data.message === "string" ? data.message : tRef.current("insufficient");
          setStreamStatus("refused");
          setMessages((current) => current.map((item) => item.id === assistant.id ? { ...item, content: textValue, state: "refused" } : item));
          return;
        }
        if (name === "done") {
          setStreamStatus("complete");
          const id = typeof data.request_id === "string" ? data.request_id : null;
          setMessages((current) => current.map((item) => item.id === assistant.id ? { ...item, request_id: id, provisional: false, state: item.state === "refused" ? "refused" : "complete" } : item));
          return;
        }
        if (name === "error") {
          const problem = typeof data.problem === "object" && data.problem !== null ? data.problem as Record<string, unknown> : {};
          throw new Error(typeof problem.detail === "string" ? problem.detail : tRef.current("networkError"));
        }
      });
      window.dispatchEvent(new Event("sagefield:conversations-changed"));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setStreamStatus("cancelled");
        setMessages((current) => current.map((item) => item.provisional ? { ...item, provisional: false, state: "cancelled" } : item));
      } else {
        setStreamStatus("error");
        setStreamError(error instanceof Error ? error.message : t("networkError"));
        setMessages((current) => current.map((item) => item.provisional && !item.content ? { ...item, content: t("networkError"), provisional: false, state: "error" } : item));
      }
    } finally { setBusy(false); setController(null); }
  }

  async function submitFeedback(message: LocalMessage, rating: "up" | "down") {
    if (!message.request_id) return;
    try {
      await apiFetch("feedback", { method: "POST", headers: { "content-type": "application/json", "idempotency-key": idempotencyKey() }, body: JSON.stringify({ request_id: message.request_id, rating }) });
      setFeedbackSent(message.request_id);
    } catch (error) { setStreamError(error instanceof Error ? error.message : t("networkError")); }
  }

  function toggleCollection(id: string) {
    setSelectedCollections(selectedCollections.includes(id) ? selectedCollections.filter((item) => item !== id) : [...selectedCollections, id].slice(0, 3));
  }

  return (
    <div className="mx-auto grid max-w-[1600px] gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
      <section className="surface flex min-h-[calc(100vh-148px)] min-w-0 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 sm:px-7">
          <div className="min-w-0"><div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-xl bg-brand-tint text-brand"><Sparkles size={16} /></span><h2 className="truncate text-sm font-semibold">{active?.title ?? t("chat")}</h2></div><p className="mt-1 pl-10 text-xs text-muted">Grounded in the collections you choose</p></div>
          <div className="relative">
            <button onClick={() => setScopeOpen(!scopeOpen)} className="secondary-button !min-h-10 gap-2 !rounded-full !px-3 text-xs"><Archive size={14} /><span>{t("scope")}: {selectedCollections.length ? `${selectedCollections.length} selected` : t("allCollections")}</span><ChevronDown size={14} /></button>
            {scopeOpen && <div className="absolute right-0 top-12 z-20 w-72 rounded-2xl border border-line bg-panel p-3 shadow-xl"><p className="px-2 pb-2 text-xs font-semibold text-muted">Choose up to three collections</p>{collections.map((item) => <label key={item.id} className="flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-2 text-sm hover:bg-panel-soft"><input type="checkbox" checked={selectedCollections.includes(item.id)} onChange={() => toggleCollection(item.id)} disabled={!selectedCollections.includes(item.id) && selectedCollections.length >= 3} className="accent-[var(--brand)]" />{item.name}</label>)}{collections.length === 0 && <p className="p-2 text-xs text-muted">Create a collection in Knowledge first.</p>}<button className="secondary-button mt-2 w-full !min-h-9 text-xs" onClick={() => setScopeOpen(false)}>Done</button></div>}
          </div>
        </div>
        <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6 sm:px-8 sm:py-8" aria-label="Conversation messages">
          {messages.length === 0 ? <div className="mx-auto flex min-h-[420px] max-w-2xl flex-col justify-center">
            <span className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-line bg-panel px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[.12em] text-brand"><Sparkles size={13} />Evidence-led answers</span>
            <h3 className="max-w-xl text-3xl font-medium leading-tight tracking-[-.04em] sm:text-[42px]">{t("empty")}</h3>
            <p className="mt-4 max-w-lg text-sm leading-6 text-muted">{t("emptyHelp")}</p>
            <div className="mt-7 grid gap-2 sm:grid-cols-2">
              {["What are our current onboarding steps?", "Summarize the latest policy update."].map((starter) => <button key={starter} className="surface-soft flex min-h-14 items-center justify-between gap-3 px-4 text-left text-sm transition-colors hover:border-brand/40 hover:bg-brand-tint" onClick={() => { setQuestion(starter); queryBox.current?.focus(); }}><span>{starter}</span><ArrowUp size={15} className="rotate-45 text-muted" /></button>)}
            </div>
          </div> : <div className="mx-auto max-w-[800px] space-y-7">
            {messages.map((message, messageIndex) => <article key={message.id} className={message.role === "user" ? "ml-auto max-w-[82%]" : "max-w-full"}>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[.12em] text-muted">{message.role === "user" ? <span className="ml-auto">You</span> : <><span className="grid h-6 w-6 place-items-center rounded-lg bg-brand-tint text-brand"><Sparkles size={13} /></span><span>Sagefield</span>{message.state === "retrieving" && <span className="font-normal normal-case tracking-normal">· {t("retrieving")}</span>}{message.state === "streaming" && <span className="font-normal normal-case tracking-normal">· {t("streaming")}</span>}</>}</div>
              <div className={message.role === "user" ? "rounded-2xl rounded-tr-md bg-brand px-4 py-3 text-sm leading-6 text-white dark:text-[#10261c]" : `prose-safe text-sm leading-7 ${message.state === "refused" ? "rounded-2xl border border-[#e7d9bc] bg-[#fcf8ef] p-4 text-[#55452d] dark:bg-[#302a1d] dark:text-[#e8d8b9]" : "px-1 py-1"}`}>
                {message.role === "user" ? <p className="whitespace-pre-wrap">{message.content}</p> : <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: () => null, a: ({ href, children }) => safeExternalLink(href, children) }}>{message.content}</ReactMarkdown>}
                {message.state === "cancelled" && <p className="mt-2 text-xs text-muted">Response stopped.</p>}
              </div>
              {message.role === "user" && !busy && <button className="mt-1 min-h-9 rounded-lg px-2 text-xs text-muted hover:bg-panel-soft hover:text-ink" onClick={() => { setQuestion(message.content); queryBox.current?.focus(); }}>{t("edit")}</button>}
              {message.role === "assistant" && message.citations.length > 0 && <div className="mt-3 flex flex-wrap gap-2" aria-label={t("citations")}>{message.citations.map((item, index) => <button key={item.chunk_id} className="inline-flex min-h-8 items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 text-xs text-muted hover:border-brand/50 hover:text-brand" onClick={() => setCitation(item)}><span className="grid h-4 w-4 place-items-center rounded-full bg-brand-tint text-[10px] font-bold text-brand">{index + 1}</span><span className="max-w-48 truncate">{item.filename}{item.page ? ` · p. ${item.page}` : ""}</span></button>)}</div>}
              {message.role === "assistant" && message.request_id && <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted"><span>{t("feedback")}</span><button className="icon-button !min-h-9 !min-w-9" aria-label="Helpful answer" onClick={() => void submitFeedback(message, "up")}><ThumbsUp size={15} /></button><button className="icon-button !min-h-9 !min-w-9" aria-label="Not helpful" onClick={() => void submitFeedback(message, "down")}><ThumbsDown size={15} /></button>{feedbackSent === message.request_id && <span className="inline-flex items-center gap-1 text-brand"><Check size={13} />{t("thanks")}</span>}<button className="ml-auto inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2 hover:bg-panel-soft" onClick={() => void navigator.clipboard.writeText(message.content)}><Files size={14} />{t("copy")}</button></div>}
              {message.role === "assistant" && message.request_id && !busy && <button className="ml-1 mt-1 min-h-9 rounded-lg px-2 text-xs text-muted hover:bg-panel-soft hover:text-ink" onClick={() => void sendQuestion(messages.slice(0, messageIndex).filter((entry) => entry.role === "user").at(-1)?.content)}>{t("retryAnswer")}</button>}
            </article>)}
          </div>}
          {streamError && <div role="alert" className="mx-auto mt-5 max-w-[800px] rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{streamError}</div>}
          {streamStatus === "error" && <div className="mx-auto mt-3 max-w-[800px]"><button className="secondary-button" onClick={() => void sendQuestion(messages.filter((item) => item.role === "user").at(-1)?.content)}>{t("retry")}</button></div>}
        </div>
        <div className="sticky bottom-0 border-t border-line bg-panel/95 px-4 py-4 backdrop-blur-lg sm:px-8 sm:py-5">
          <form className="mx-auto max-w-[820px]" onSubmit={(event: FormEvent) => { event.preventDefault(); void sendQuestion(); }}>
            <div className="rounded-[1.2rem] border border-line bg-panel p-2 shadow-[0_8px_28px_rgba(26,54,39,.07)] focus-within:border-brand/50 focus-within:ring-2 focus-within:ring-brand/10">
              <textarea ref={queryBox} value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onComposerKey} rows={2} maxLength={8000} placeholder={t("placeholder")} aria-label={t("placeholder")} className="max-h-40 min-h-12 w-full resize-y bg-transparent px-3 py-2 text-sm leading-6 outline-none placeholder:text-muted/80" />
              <div className="flex items-center justify-between gap-2 px-1 pb-0.5"><p className="text-[11px] text-muted">{selectedCollections.length ? `${selectedCollections.length} collections selected` : "Select a collection to begin"}</p><div className="flex items-center gap-2">{busy && <button type="button" className="secondary-button !min-h-10" onClick={() => controller?.abort()}><X size={15} />{t("stop")}</button>}<button type="submit" className="primary-button !min-h-10 !rounded-xl !px-3.5" disabled={busy || !question.trim()} aria-label={t("send")}>{busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white dark:border-t-[#10261c]" /> : <ArrowUp size={17} />}</button></div></div>
            </div>
            <p className="mt-2 text-center text-[10px] text-muted">Review citations before acting. Sagefield answers only from sources available in your workspace.</p>
          </form>
        </div>
      </section>
      <aside className="hidden xl:block">
        <div className="surface sticky top-[92px] min-h-[300px] overflow-hidden">
          <div className="border-b border-line px-5 py-4"><p className="text-xs font-semibold uppercase tracking-[.15em] text-muted">{t("citations")}</p><h2 className="mt-1 text-base font-semibold">Source notes</h2></div>
          {citation ? <CitationDetail citation={citation} t={t} onClose={() => setCitation(null)} /> : <div className="flex min-h-[250px] flex-col items-center justify-center px-7 text-center"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-tint text-brand"><BookOpenCheck size={20} /></span><p className="mt-4 text-sm font-semibold">Sources stay in view</p><p className="mt-2 text-xs leading-5 text-muted">Choose a citation in an answer to inspect the supporting passage, page and document.</p></div>}
        </div>
        <div className="mt-4 rounded-2xl border border-[#e6dcc8] bg-[#fbf7ee] p-4 text-[#5c513f] dark:border-[#574b35] dark:bg-[#29251d] dark:text-[#d9cba9]"><div className="flex items-center gap-2 text-xs font-semibold"><ShieldCheck size={15} />Evidence first</div><p className="mt-2 text-xs leading-5">If sources do not support a confident answer, Sagefield will say so.</p></div>
      </aside>
      <Dialog.Root open={Boolean(citation)} onOpenChange={(open) => !open && setCitation(null)}>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 xl:hidden" /><Dialog.Content className="fixed inset-x-0 bottom-0 z-50 max-h-[82vh] overflow-y-auto rounded-t-[1.5rem] border border-line bg-panel p-5 shadow-2xl xl:hidden"><Dialog.Title className="sr-only">{t("citations")}</Dialog.Title>{citation && <CitationDetail citation={citation} t={t} onClose={() => setCitation(null)} />}</Dialog.Content></Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root open={showHelp} onOpenChange={setShowHelp}>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/35" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-panel p-6 shadow-2xl"><Dialog.Title className="text-lg font-semibold">{t("keyboard")}</Dialog.Title><p className="mt-3 text-sm leading-6 text-muted">{t("keyboardHelp")}</p><Dialog.Close className="secondary-button mt-5">{t("cancel")}</Dialog.Close></Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function safeExternalLink(href: string | undefined, children: React.ReactNode) {
  if (!href) return <>{children}</>;
  let url: URL;
  try { url = new URL(href, "https://workspace.invalid"); } catch { return <>{children}</>; }
  if (url.protocol !== "https:" && url.protocol !== "http:") return <span>{children}</span>;
  if (url.hostname === "workspace.invalid") return <a href={`${url.pathname}${url.search}${url.hash}`}>{children}</a>;
  return <a href={url.toString()} target="_blank" rel="noopener noreferrer" aria-label={`${children?.toString() ?? "Link"} (${url.hostname})`}>{children}<span className="ml-1 text-[10px] text-muted">↗ {url.hostname}</span></a>;
}

function CitationDetail({ citation, t, onClose }: { citation: Citation; t: ReturnType<typeof useTranslations>; onClose: () => void }) {
  return <div className="p-5"><div className="flex items-start justify-between gap-3"><div><p className="text-[11px] font-semibold uppercase tracking-[.14em] text-brand">{t("sourcePassage")}</p><h3 className="mt-2 text-sm font-semibold leading-5">{citation.filename}</h3><p className="mt-1 text-xs text-muted">{citation.page ? `Page ${citation.page}` : "Page unavailable"}{citation.section ? ` · ${citation.section}` : ""}</p></div><button className="icon-button !min-h-9 !min-w-9 xl:hidden" onClick={onClose} aria-label={t("cancel")}><X size={17} /></button></div><blockquote className="mt-5 rounded-xl border-l-[3px] border-gold bg-panel-soft px-4 py-3 text-sm leading-6">{citation.quote}</blockquote><p className="mt-4 text-[11px] leading-5 text-muted">This passage is shown as plain text from a tenant-authorized source.</p></div>;
}

function SettingsPanel({ t, email, locale }: { t: ReturnType<typeof useTranslations>; email: string; locale: string }) {
  const { theme, setTheme } = useTheme();
  return <section className="surface mx-auto max-w-3xl p-5 sm:p-8"><div className="mb-7"><p className="text-xs font-semibold uppercase tracking-[.15em] text-brand">Personal workspace</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">{t("settings")}</h2></div><div className="divide-y divide-line">
    <div className="flex flex-wrap items-center justify-between gap-4 py-5"><div><h3 className="text-sm font-semibold">{t("theme")}</h3><p className="mt-1 text-xs text-muted">Choose an appearance for this browser.</p></div><select className="field !w-auto min-w-36" value={theme ?? "system"} onChange={(event) => setTheme(event.target.value)} aria-label={t("theme")}><option value="light">{t("light")}</option><option value="dark">{t("dark")}</option><option value="system">{t("system")}</option></select></div>
    <div className="flex flex-wrap items-center justify-between gap-4 py-5"><div><h3 className="text-sm font-semibold">{t("language")}</h3><p className="mt-1 text-xs text-muted">Interface text and regional formatting.</p></div><a className="secondary-button" href={locale === "en" ? "/sw" : "/en"}>{locale === "en" ? "Kiswahili" : "English"}</a></div>
    <div className="py-5"><h3 className="text-sm font-semibold">Account</h3><p className="mt-1 text-sm text-muted">{email}</p><p className="mt-1 text-xs text-muted">Signed in with your approved Google identity.</p><button className="secondary-button mt-3" onClick={() => void signOut({ redirectTo: `/${locale}/login` })}><LogOut size={15} />{t("signOut")}</button></div>
    <div className="py-5"><h3 className="text-sm font-semibold">{t("retention")}</h3><p className="mt-2 max-w-xl text-sm leading-6 text-muted">{t("retentionInfo")}</p></div>
  </div></section>;
}
