const uuid =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const rules: [string, string][] = [
  ["GET", "me"],
  ["GET", "subjects|publication-types|outlets"],
  ["GET", `templates/${uuid}`],
  ["POST", "auth/(register|verify-email|forgot-password|reset-password)"],
  ["GET|POST", "articles"],
  ["GET|PATCH", `articles/${uuid}`],
  ["POST", `articles/${uuid}/(submit|resubmit|claim|conflicts)`],
  ["GET|POST", `articles/${uuid}/versions`],
  ["PATCH", `articles/${uuid}/versions/${uuid}`],
  ["GET", `articles/${uuid}/(timeline|invoice)`],
  ["GET|PUT", "reviewers/me/subjects"],
  ["PATCH", "reviewers/me/availability"],
  ["GET", "review-queue|assignments/me"],
  ["POST", `assignments/${uuid}/(start|release|review)`],
  ["PUT", `assignments/${uuid}/review-draft`],
  ["GET|POST", `invoices/${uuid}/payment-attempts`],
  ["POST", "files"],
  ["GET", `files/${uuid}/download`],
  ["GET", "notifications"],
  ["POST", `notifications/${uuid}/read`],
  ["GET", "admin/(users|reviewers|articles|payments|audit-events)"],
  ["POST", "admin/reviewer-invitations"],
  ["POST", `admin/reviewers/${uuid}/(approve|reject)`],
  ["PATCH", `admin/users/${uuid}`],
  ["DELETE", `admin/articles/${uuid}`],
  ["GET", `admin/articles/${uuid}/reviewers`],
  ["POST", `admin/articles/${uuid}/(assign|reassign|publish|verify-and-publish)`],
  ["POST", `admin/assignments/${uuid}/extend`],
  ["POST", `admin/payment-attempts/${uuid}/(verify|reject)`],
  ["GET|POST", "admin/settings"],
  ["GET|POST", "admin/(subjects|outlets|templates|issues)"],
  ["PATCH", `admin/(subjects|outlets|issues)/${uuid}`],
  ["GET", "public/articles"],
  ["GET", "public/articles/[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}(/file)?"],
];
export function allowed(method: string, path: string) {
  return rules.some(
    ([methods, pattern]) =>
      methods.split("|").includes(method) &&
      new RegExp(`^(?:${pattern})$`).test(path),
  );
}
export function publicPath(path: string) {
  return /^(?:public\/articles(?:\/[^/]+(?:\/file)?)?|subjects|publication-types|outlets|auth\/(?:register|verify-email|forgot-password|reset-password))$/.test(
    path,
  );
}
