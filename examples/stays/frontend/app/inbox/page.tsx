import Link from "next/link"

import { ScreenState } from "@/components/stays/screen-state"
import { TripStatusBadge } from "@/components/stays/trip-status"
import { stays } from "@/lib/stays"
import { dateTime, shortDate } from "@/lib/format"
import type { Thread } from "@/lib/types"

export default async function InboxPage() {
  const { threads } = await stays<{ threads: Thread[] }>("/api/inbox")
  return (
    <div className="flex flex-col gap-6">
      <ScreenState name="inbox" value={{ threads: threads.map((t) => `${t.trip_id} ${t.host}: ${t.last_message.slice(0, 60)}`) }} />
      <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
      {threads.length ? (
        <ul className="divide-y rounded-2xl border bg-card" data-testid="inbox">
          {threads.map((t) => (
            <li key={t.trip_id}>
              <Link href={`/trips/${t.trip_id}`} className="flex items-start gap-4 px-5 py-4 hover:bg-muted/50">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 font-semibold text-primary">{t.host[0]}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{t.host}</span>
                    <TripStatusBadge status={t.status} />
                  </span>
                  <span className="block truncate text-sm text-muted-foreground">
                    {t.last_from === "guest" ? "You: " : ""}
                    {t.last_message}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {t.title} · {shortDate(t.check_in)}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">{dateTime(t.last_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No messages yet.</p>
      )}
    </div>
  )
}
