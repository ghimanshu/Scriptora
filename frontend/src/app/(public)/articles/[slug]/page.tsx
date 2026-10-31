import { PublicFrame } from "@/components/common/public";
import { PublicArticle } from "@/components/articles/catalog";
export default async function Page({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  return (
    <PublicFrame>
      <PublicArticle slug={(await params).slug} />
    </PublicFrame>
  );
}
