import "server-only";
import { z } from "zod";

const apiCredentialSchema = z.object({ api_key: z.string().min(1).max(256), role: z.enum(["viewer", "editor", "admin"]) }).strict();
const directorySchema = z.record(z.string().email(), apiCredentialSchema);
const keyPattern = /^rag\.[0-9a-f-]{36}\.[0-9a-f-]{36}\.[A-Za-z0-9_-]{32,}$/i;

export type WebIdentity = z.infer<typeof apiCredentialSchema> & { email: string };

function readDirectory(): Record<string, z.infer<typeof apiCredentialSchema>> {
  const raw = process.env.WEB_IDENTITY_DIRECTORY_JSON;
  if (!raw) return {};
  let parsed: unknown;
  try { parsed = JSON.parse(raw); }
  catch { throw new Error("WEB_IDENTITY_DIRECTORY_JSON must be valid JSON"); }
  const directory = directorySchema.parse(parsed);
  const credentials = Object.values(directory).map((identity) => identity.api_key);
  if (new Set(credentials).size !== credentials.length) throw new Error("Each approved Google identity must have its own API key");
  for (const identity of Object.values(directory)) {
    if (!keyPattern.test(identity.api_key)) throw new Error("The mapped workspace credential is malformed");
  }
  return directory;
}

export function identityForEmail(email: string): WebIdentity | null {
  const normalized = email.trim().toLowerCase();
  const match = Object.entries(readDirectory()).find(([address]) => address.toLowerCase() === normalized);
  return match ? { email: match[0].toLowerCase(), ...match[1] } : null;
}
