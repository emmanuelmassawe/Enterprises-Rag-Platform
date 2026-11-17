import "server-only";
import { z } from "zod";

const directorySchema = z.record(z.string().email(), z.string().min(1).max(256));
const keyPattern = /^rag\.[0-9a-f-]{36}\.[0-9a-f-]{36}\.[A-Za-z0-9_-]{32,}$/i;

export function apiKeyForEmail(email: string): string | null {
  const raw = process.env.WEB_IDENTITY_API_KEYS_JSON;
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("WEB_IDENTITY_API_KEYS_JSON must be valid JSON");
  }
  const directory = directorySchema.parse(parsed);
  const matchingEntry = Object.entries(directory).find(([address]) => address.toLowerCase() === email.trim().toLowerCase());
  if (!matchingEntry) return null;
  const [, apiKey] = matchingEntry;
  if (!keyPattern.test(apiKey)) throw new Error("The mapped workspace credential is malformed");
  return apiKey;
}
