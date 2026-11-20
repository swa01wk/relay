import { RelationSelect } from "@/components/vnb/fields"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { dmy, inr } from "@/lib/format"
import type { NpsDetails } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function NpsPage() {
  const nps = await read<NpsDetails>("get_nps_details")
  return (
    <>
      <div className="gv-msg-info">
        <b>National Pension System (NPS).</b> {nps.rules.tax}. Your age: {nps.your_age} ({nps.years_to_60} years to 60). At your slab the extra deduction saves about ₹
        {inr(nps.tax_saving_per_year, false)} a year. Returns are market-linked.
      </div>
      {nps.account ? (
        <>
          <Box title="My NPS Account (Tier I)">
            <table className="gv-form">
              <tbody>
                <Row label="PRAN">{nps.account.pran}</Row>
                <Row label="Investment choice">{nps.account.choice}</Row>
                <Row label="Contributed (total)">₹{inr(nps.account.contributed, false)}</Row>
                <Row label="Contributed this financial year">₹{inr(nps.account.this_fy, false)}</Row>
                <Row label="Opened">{dmy(nps.account.opened)}</Row>
                <Row label="Nominee">{nps.account.nominee}</Row>
              </tbody>
            </table>
          </Box>
          <Box title="Contribute to NPS" id="contribute">
            <ToolForm tool="contribute_to_nps" name="Contribute to NPS" submitLabel="Contribute">
              <Row label="Amount (₹)" required hint={`Minimum ₹${nps.rules.min_contribution}`}>
                <input name="amount" type="number" min={nps.rules.min_contribution} className="gv-input w-32" />
              </Row>
            </ToolForm>
          </Box>
        </>
      ) : (
        <Box title="Open NPS Account (Tier I) — eNPS" id="open-nps">
          <ToolForm tool="open_nps_account" name="Open NPS account" submitLabel="Open Account" agree="I have read the NPS offer document. I understand withdrawals are restricted until 60 and 40% must buy an annuity.">
            <Row label="Investment choice" required>
              <select name="investment_choice" className="gv-input max-w-full">
                {Object.entries(nps.rules.choices).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="First contribution (₹)" required hint={`Minimum ₹${inr(nps.rules.min_opening, false)}`}>
              <input name="initial_contribution" type="number" min={nps.rules.min_opening} className="gv-input w-32" />
            </Row>
            <Row label="Nominee" required>
              <input name="nominee_name" className="gv-input w-56" />
            </Row>
            <Row label="Relationship" required>
              <RelationSelect />
            </Row>
          </ToolForm>
        </Box>
      )}
    </>
  )
}
