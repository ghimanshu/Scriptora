import { ReviewWorkspace } from "@/components/reviews/workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ReviewWorkspace id={(await params).id} />;
}
