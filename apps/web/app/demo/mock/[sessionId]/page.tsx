import { redirect } from "next/navigation";

export default async function LegacyMockDemoPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  redirect(`/play/snow-village/${encodeURIComponent(sessionId)}`);
}
