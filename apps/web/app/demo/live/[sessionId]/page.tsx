import { redirect } from "next/navigation";

export default async function LegacyLiveDemoPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  redirect(`/play/snow-village/${encodeURIComponent(sessionId)}`);
}
