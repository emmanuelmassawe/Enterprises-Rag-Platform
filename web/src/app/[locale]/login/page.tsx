import { ArrowUpRight, BookOpenCheck, ShieldCheck } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { signIn } from "@/auth";

export default async function LoginPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("common");
  return (
    <main className="min-h-screen bg-canvas px-5 py-8 text-ink">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center justify-center">
        <section className="grid w-full overflow-hidden rounded-[2rem] border border-line bg-panel shadow-[0_30px_100px_rgba(29,67,48,.12)] lg:grid-cols-[1.1fr_.9fr]">
          <div className="relative hidden min-h-[620px] overflow-hidden bg-[#173e31] p-12 text-[#f2f6f1] lg:flex lg:flex-col lg:justify-between">
            <div className="absolute -right-20 -top-20 h-96 w-96 rounded-full border border-white/10" />
            <div className="absolute -bottom-40 -left-12 h-[34rem] w-[34rem] rounded-full border border-white/10" />
            <div className="relative flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#bdd5c3] text-[#173e31]"><BookOpenCheck size={22} /></span><span className="text-lg font-semibold tracking-tight">{t("product")}</span></div>
            <div className="relative max-w-lg">
              <p className="mb-5 text-xs font-semibold uppercase tracking-[.22em] text-[#bdd5c3]">A calmer way to find what matters</p>
              <h1 className="text-5xl font-medium leading-[1.08] tracking-[-.04em]">Know where your answers come from.</h1>
              <p className="mt-6 max-w-md text-base leading-7 text-[#d1ded5]">Bring your team's trusted documents into one thoughtful workspace. Every answer stays connected to its source.</p>
            </div>
            <div className="relative flex items-center gap-2 text-sm text-[#c4d5ca]"><ShieldCheck size={17} />Private by design · evidence in view</div>
          </div>
          <div className="flex min-h-[620px] flex-col justify-center p-7 sm:p-12 lg:p-16">
            <div className="mb-12 flex items-center gap-3 lg:hidden"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-brand text-white"><BookOpenCheck size={22} /></span><span className="text-lg font-semibold">{t("product")}</span></div>
            <p className="text-xs font-semibold uppercase tracking-[.2em] text-brand">Your team's knowledge, considered</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">Welcome to your workspace</h2>
            <p className="mt-4 max-w-sm leading-7 text-muted">{t("signInHelp")}</p>
            <form action={async () => { "use server"; await signIn("google", { redirectTo: `/${locale}` }); }} className="mt-9">
              <button className="secondary-button w-full justify-center gap-3" type="submit"><GoogleMark />{t("signIn")}<ArrowUpRight className="ml-auto text-muted" size={17} /></button>
            </form>
            <p className="mt-6 text-xs leading-5 text-muted">Only accounts approved by your workspace administrator can sign in. Your Google credentials are never shared with the assistant.</p>
          </div>
        </section>
      </div>
    </main>
  );
}

function GoogleMark() {
  return <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 24.5c0-1.4-.1-2.8-.4-4.1H24v7.8h11a9.4 9.4 0 0 1-4.1 6.2v5.1h6.6c3.9-3.6 6.1-8.8 6.1-15Z"/><path fill="#34A853" d="M24 44c5.5 0 10.1-1.8 13.5-4.9l-6.6-5.1c-1.8 1.2-4.1 2-6.9 2-5.3 0-9.8-3.6-11.4-8.4H5.8v5.3A20 20 0 0 0 24 44Z"/><path fill="#4285F4" d="M12.6 27.6a12 12 0 0 1 0-7.2v-5.3H5.8a20 20 0 0 0 0 17.8l6.8-5.3Z"/><path fill="#EA4335" d="M24 12c3 0 5.7 1 7.8 3l5.8-5.8A19.5 19.5 0 0 0 24 4 20 20 0 0 0 5.8 15.1l6.8 5.3C14.2 15.6 18.7 12 24 12Z"/></svg>;
}
