import type { ArticleStatus } from "@/types/api";
export const statusLabels: Record<ArticleStatus, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  ASSIGNED: "Assigned",
  REJECTED: "Rejected (changes requested)",
  APPROVED: "Approved",
  PAID: "Paid (awaiting verification)",
  PAYMENT_APPROVED: "Payment approved",
  PUBLISH: "Published",
};
export function money(amount: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}
export function date(value?: string) {
  return value
    ? new Date(value).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";
}
export function deadline(value: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
