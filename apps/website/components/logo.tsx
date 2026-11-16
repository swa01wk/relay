/** Relay mark: two nodes and the signal between them. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden="true">
        <rect x="1" y="1" width="22" height="22" rx="6" fill="var(--accent)" />
        <circle cx="7.5" cy="12" r="2.25" fill="var(--accent-fg)" />
        <circle cx="16.5" cy="12" r="2.25" fill="var(--accent-fg)" />
        <path d="M10 12h4" stroke="var(--accent-fg)" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="1.2 1.8" />
      </svg>
      Relay
    </span>
  )
}
