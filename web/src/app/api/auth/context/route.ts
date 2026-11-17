import { auth } from "@/auth";
import { identityForEmail } from "@/lib/server/identity-directory";

export const dynamic = "force-dynamic";

export async function GET() {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return Response.json({ code: "authentication_required" }, { status: 401 });
  const identity = identityForEmail(email);
  if (!identity) return Response.json({ code: "authentication_required" }, { status: 401 });
  return Response.json({ email: identity.email, role: identity.role }, { headers: { "cache-control": "no-store" } });
}
