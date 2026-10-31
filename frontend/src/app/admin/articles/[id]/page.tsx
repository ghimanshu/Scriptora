import { ArticleWorkspace } from "@/components/articles/workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ArticleWorkspace id={(await params).id} admin />;
}
