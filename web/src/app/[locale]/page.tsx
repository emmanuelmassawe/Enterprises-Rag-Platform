import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { Workspace } from "@/components/workspace/workspace";

export default async function WorkspacePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const session = await auth();
  if (!session?.user?.email) redirect(`/${locale}/login`);
  return <Workspace locale={locale} email={session.user.email} displayName={session.user.name ?? session.user.email} />;
}
