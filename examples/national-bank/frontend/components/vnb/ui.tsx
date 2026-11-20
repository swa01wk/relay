import * as React from "react"

/** A boxed panel with the portal's maroon title bar. */
export function Box({ title, help, id, children, className }: { title: React.ReactNode; help?: React.ReactNode; id?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`gv-box ${className ?? ""}`} id={id} aria-label={typeof title === "string" ? title : undefined}>
      <div className="gv-box-title">
        <span>{title}</span>
        {help && <span className="gv-help">{help}</span>}
      </div>
      <div className="gv-box-body">{children}</div>
    </section>
  )
}

/** A label cell + field cell row of a portal form table. */
export function Row({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: React.ReactNode }) {
  return (
    <tr>
      <td className="gv-label">
        {label}
        {required && <span className="gv-req"> *</span>}
      </td>
      <td>
        {children}
        {hint && <div className="gv-note">{hint}</div>}
      </td>
    </tr>
  )
}

export function New() {
  return <span className="gv-new">New</span>
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="gv-note">{children}</p>
}
