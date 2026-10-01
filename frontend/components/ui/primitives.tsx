import Link from "next/link";
import { ArrowUpRight, Inbox } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props} />
  );
}
export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function StatusBadge({ status }: { status: string }) {
  const text: Record<string, string> = {
    healthy: "Healthy",
    degraded: "Degraded",
    failing: "Issue",
    unsupported: "Unsupported",
    active: "Active",
    inactive: "Inactive",
    new: "New",
    saved: "Saved",
    applied: "Applied",
    ignored: "Ignored",
    open: "Open",
    closed: "Closed",
  };
  return (
    <span className={`badge status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {text[status] || "Not checked"}
    </span>
  );
}
export function ScoreBadge({ score }: { score: number }) {
  return (
    <span
      className="score-badge"
      aria-label={`Match score ${score} out of 100`}
    >
      <strong>{Math.round(score)}</strong>
      <span>match</span>
    </span>
  );
}
export function ExternalLink({
  url,
  children,
  primary = false,
}: {
  url: string | null;
  children: ReactNode;
  primary?: boolean;
}) {
  return url && /^https?:\/\//i.test(url) ? (
    <a
      className={`button button-${primary ? "primary" : "secondary"}`}
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <ArrowUpRight size={15} aria-hidden="true" />
      <span className="sr-only"> (opens in new tab)</span>
    </a>
  ) : null;
}
export function EmptyState({
  title,
  description,
  href,
  action,
}: {
  title: string;
  description: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={28} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {href && (
        <Link prefetch={false} className="button button-primary" href={href}>
          {action}
        </Link>
      )}
    </div>
  );
}
export function LoadingSkeleton() {
  return (
    <div role="status" aria-label="Loading page" className="skeleton-list">
      <span className="sr-only">Loading…</span>
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="skeleton-row">
          <div className="skeleton skeleton-title" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-short" />
        </div>
      ))}
    </div>
  );
}
export function Pagination({
  page,
  totalPages,
  hasNext,
  query = {},
}: {
  page: number;
  totalPages?: number;
  hasNext?: boolean;
  query?: Record<string, string>;
}) {
  const href = (next: number) =>
    `?${new URLSearchParams({ ...query, page: String(next) })}`;
  return (
    <nav className="pagination" aria-label="Pagination">
      {page > 1 ? (
        <a className="button button-secondary" href={href(page - 1)}>
          Previous
        </a>
      ) : (
        <span className="button disabled" aria-disabled="true">
          Previous
        </span>
      )}
      <span>
        Page {page}
        {totalPages !== undefined ? ` of ${Math.max(1, totalPages)}` : ""}
      </span>
      {(totalPages !== undefined ? page < totalPages : hasNext) ? (
        <a className="button button-secondary" href={href(page + 1)}>
          Next
        </a>
      ) : (
        <span className="button disabled" aria-disabled="true">
          Next
        </span>
      )}
    </nav>
  );
}
export function DateText({
  value,
  withTime = false,
}: {
  value: string | null;
  withTime?: boolean;
}) {
  return value ? (
    <time dateTime={value}>
      {new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
        ...(withTime
          ? { hour: "2-digit", minute: "2-digit", hour12: false }
          : {}),
      }).format(new Date(value))}
      {withTime && " UTC"}
    </time>
  ) : (
    <span>Not checked yet</span>
  );
}
