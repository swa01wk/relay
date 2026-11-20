"use client"

import * as React from "react"

import { ToolForm } from "@/components/vnb/tool-form"
import { Row } from "@/components/vnb/ui"

/** Register a biller — the provider list depends on the category, as on BBPS. */
export function AddBillerForm({ categories, providers }: { categories: Record<string, string>; providers: Record<string, string[]> }) {
  const [category, setCategory] = React.useState("")
  return (
    <ToolForm tool="add_biller" name="Add biller" submitLabel="Register Biller">
      <Row label="Biller category" required>
        <select name="category" value={category} onChange={(e) => setCategory(e.target.value)} className="gv-input">
          <option value="">-- Select --</option>
          {Object.entries(categories).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Biller" required>
        <select name="provider" className="gv-input" key={category}>
          <option value="">-- Select --</option>
          {(providers[category] ?? Object.values(providers).flat()).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Consumer / account number" required hint="As printed on your bill">
        <input name="consumer_number" className="gv-input w-48" />
      </Row>
      <Row label="Nickname">
        <input name="nickname" maxLength={30} className="gv-input w-40" />
      </Row>
    </ToolForm>
  )
}
