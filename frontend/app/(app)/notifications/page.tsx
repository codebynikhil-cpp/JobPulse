import { load, pageNumber, queryValues, type Search } from "@/lib/product-api";
import type { Notice } from "@/types/product";
import NotificationRow from "@/components/notifications/NotificationRow";
import ReadAllButton from "@/components/notifications/ReadAllButton";
import { EmptyState, PageHeader, Pagination } from "@/components/ui/primitives";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const values = queryValues(await searchParams),
    page = pageNumber(values.page);
  const query = new URLSearchParams({
    limit: "21",
    offset: String((page - 1) * 20),
  });
  if (values.is_read === "false" || values.is_read === "true")
    query.set("is_read", values.is_read);
  const notices = await load<Notice[]>(`/api/notifications?${query}`);
  return (
    <>
      <PageHeader
        title="Notifications"
        description="Relevant opportunities, without the noise."
        action={<ReadAllButton />}
      />
      <nav className="tabs" aria-label="Notification filter">
        {[
          { label: "All", value: "" },
          { label: "Unread", value: "false" },
          { label: "Read", value: "true" },
        ].map((tab) => (
          <a
            key={tab.label}
            href={tab.value ? `?is_read=${tab.value}` : "/notifications"}
            aria-current={
              (values.is_read || "") === tab.value ? "page" : undefined
            }
          >
            {tab.label}
          </a>
        ))}
      </nav>
      {notices.length ? (
        <div className="notice-list">
          {notices.slice(0, 20).map((notice) => (
            <NotificationRow key={notice.id} notice={notice} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="You're all caught up"
          description="Matching job alerts will appear here as your companies are monitored."
        />
      )}
      <Pagination page={page} hasNext={notices.length > 20} query={values} />
    </>
  );
}
