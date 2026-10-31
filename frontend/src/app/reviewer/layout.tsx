import { Shell } from "@/components/common/shell";
export default function Layout({ children }: { children: React.ReactNode }) {
  return <Shell area="reviewer">{children}</Shell>;
}
