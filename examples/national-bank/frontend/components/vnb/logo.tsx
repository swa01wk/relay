/** Vasundhara National Bank's (made-up) mark: a saffron sun over a green field in a maroon ring. */
export function Logo({ size = 44, withName = true }: { size?: number; withName?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="24" cy="24" r="22" fill="#6e1423" />
        <circle cx="24" cy="24" r="17" fill="#fff" />
        <circle cx="24" cy="21" r="7" fill="#e39b2d" />
        <path d="M8 29 Q24 22 40 29 L40 34 Q24 41 8 34 Z" fill="#2f6b2f" />
        <path d="M14 30 Q24 26 34 30" stroke="#fff" strokeWidth="1.5" fill="none" />
      </svg>
      {withName && (
        <span className="flex flex-col leading-tight">
          <span style={{ fontFamily: "Georgia, serif", fontSize: size * 0.42, fontWeight: 700, color: "#6e1423" }}>Vasundhara National Bank</span>
          <span style={{ fontSize: size * 0.24, color: "#2f6b2f", fontWeight: 600 }}>वसुंधरा नेशनल बैंक · Serving the nation since 1956</span>
        </span>
      )}
    </span>
  )
}
