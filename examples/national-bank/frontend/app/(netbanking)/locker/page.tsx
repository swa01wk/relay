import { RelationSelect } from "@/components/vnb/fields"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { LockerInfo } from "@/lib/types"
import { read } from "@/lib/vnb"

const label = (size: string) => size.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())

export default async function LockerPage() {
  const info = await read<LockerInfo>("get_locker_availability")
  return (
    <>
      <Box title={`Safe Deposit Lockers — ${info.branch}`}>
        <table className="gv-table">
          <thead>
            <tr>
              <th>Size</th>
              <th className="num">Rent / year</th>
              <th className="num">With 18% GST</th>
              <th>Availability</th>
            </tr>
          </thead>
          <tbody>
            {info.sizes.map((s) => (
              <tr key={s.size}>
                <td>{label(s.size)}</td>
                <td className="num">{inr(s.rent_per_year)}</td>
                <td className="num">{inr(s.rent_with_gst)}</td>
                <td>{s.available > 0 ? `${s.available} available` : `Waiting list: ${s.waitlist}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="gv-note mt-1">{info.rule}</p>
      </Box>
      {info.yours.length > 0 && (
        <Box title="My Locker">
          <table className="gv-table">
            <tbody>
              {info.yours.map((l) => (
                <tr key={l.id}>
                  <td>{label(l.size)}</td>
                  <td>{l.status === "allotted" ? `Allotted — locker ${l.locker_number}, renews ${dmy(l.renews)}` : `Waiting list position ${l.position}`}</td>
                  <td>Since {dmy(l.since)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Box>
      )}
      <Box title="Apply for Locker" id="apply-locker">
        <ToolForm tool="apply_for_locker" name="Apply for locker" submitLabel="Apply" agree="I agree to the locker agreement as per RBI guidelines and to pay the rent annually in advance.">
          <Row label="Locker size" required>
            <select name="size" className="gv-input">
              {info.sizes.map((s) => (
                <option key={s.size} value={s.size}>
                  {label(s.size)} — ₹{inr(s.rent_with_gst, false)} a year
                </option>
              ))}
            </select>
          </Row>
          <Row label="Nominee">
            <input name="nominee_name" className="gv-input w-56" />
          </Row>
          <Row label="Relationship">
            <RelationSelect />
          </Row>
        </ToolForm>
      </Box>
    </>
  )
}
