// UI-facing contract assumptions. Replace/adapt these after backend OpenAPI generation.
export type Role = "AUTHOR" | "REVIEWER" | "ADMIN";
export type ArticleStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "REVIEWED"
  | "APPROVED"
  | "PUBLISH";
export interface User {
  id: string;
  name: string;
  email: string;
  roles: Role[];
}
export interface Taxon {
  id: string;
  name: string;
  template_id?: string;
  type_id?: string;
}
export interface Article {
  id: string;
  title: string;
  abstract?: string;
  status: ArticleStatus;
  primary_subject_id?: string;
  subject?: string;
  outlet?: string;
  created_at: string;
  lock_version: number;
  current_version_number: number;
  current_version_id?: string;
  current_version?: {
    data: {
      title: string;
      abstract: string;
      keywords: string[];
      authors: { name: string; email: string; affiliation: string }[];
      declarations: Record<string, boolean>;
    };
    manuscript_file_id?: string | null;
  };
  approved_version_id?: string;
  allowed_actions: string[];
  assignment?: Assignment;
  author_names?: string[];
  slug?: string;
  published_at?: string;
}
export interface Assignment {
  id: string;
  article_id: string;
  title?: string;
  state: string;
  due_at: string;
  article?: Article;
}
export interface Review {
  id: string;
  decision: string;
  summary: string;
  comments: {
    id: string;
    section_ref: string;
    text: string;
    required: boolean;
  }[];
}
export interface Version {
  id: string;
  version_number: number;
  manuscript_file_id?: string;
  reviews?: Review[];
  created_at: string;
}
export interface TimelineEvent {
  id: string;
  created_at: string;
  label?: string;
  event_type?: string;
  description?: string;
}
export interface Invoice {
  id: string;
  amount_minor: number;
  currency: string;
  status: string;
  instructions: string;
  payment_attempts?: PaymentAttempt[];
}
export interface PaymentAttempt {
  id: string;
  invoice_id: string;
  article_id?: string;
  status: string;
  reference: string;
  amount_minor: number;
  currency: string;
  proof_file_id: string;
  reason?: string;
}
export interface Notification {
  id: string;
  title: string;
  message: string;
  read_at?: string;
  created_at: string;
}
export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}
export interface Upload {
  id: string;
  scan_status: string;
}
