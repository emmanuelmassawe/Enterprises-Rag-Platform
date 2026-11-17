import { z } from "zod";

export const problemSchema = z.object({ code: z.string().optional(), detail: z.string().optional(), title: z.string().optional() }).passthrough();
export type ApiProblem = z.infer<typeof problemSchema>;

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/rag/v1/${path.replace(/^\//, "")}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    const problem = problemSchema.safeParse(payload);
    throw new Error(problem.success ? problem.data.detail ?? problem.data.title ?? "The request could not be completed." : "The request could not be completed.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function idempotencyKey(): string {
  return crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", "");
}

export type Page<T> = { items: T[]; page: { next_cursor: string | null; has_more: boolean } };
export type Collection = { id: string; name: string; description: string | null };
export type Conversation = { id: string; title: string; pinned: boolean; created_at: string; updated_at: string };
export type Citation = { chunk_id: string; document_id: string; filename: string; page: number | null; section: string | null; quote: string };
export type Message = { id: string; role: "user" | "assistant"; content: string; citations: Citation[]; request_id: string | null; created_at: string };

export async function streamQuery(
  body: { question: string; collection_ids: string[]; conversation_id: string; stream: true },
  signal: AbortSignal,
  onEvent: (name: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const response = await fetch("/api/rag/v1/query", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    const payload: unknown = await response.json().catch(() => ({}));
    const issue = problemSchema.safeParse(payload);
    throw new Error(issue.success ? issue.data.detail ?? "The question could not be answered." : "The question could not be answered.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = block.split("\n").find((line) => line.startsWith("event: "))?.slice(7) ?? "message";
      const dataText = block.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
      if (dataText) {
        try {
          const data: unknown = JSON.parse(dataText);
          if (typeof data === "object" && data !== null && !Array.isArray(data)) onEvent(event, data as Record<string, unknown>);
        } catch { throw new Error("The answer stream returned an invalid event."); }
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}
