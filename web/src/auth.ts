import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { apiKeyForEmail } from "@/lib/server/identity-directory";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  trustHost: process.env.AUTH_TRUST_HOST === "true",
  pages: { signIn: "/en/login" },
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  callbacks: {
    async signIn({ user, account, profile }) {
      if (account?.provider !== "google" || !user.email) return false;
      const googleProfile = profile as { email_verified?: boolean } | undefined;
      return googleProfile?.email_verified === true && apiKeyForEmail(user.email) !== null;
    },
    async session({ session }) {
      if (session.user) {
        session.user.name = session.user.name?.slice(0, 160) ?? "Workspace member";
        session.user.email = session.user.email?.toLowerCase() ?? null;
      }
      return session;
    },
  },
});
