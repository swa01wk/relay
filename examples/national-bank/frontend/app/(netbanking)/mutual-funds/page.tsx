import { AccountSelect } from "@/components/vnb/fields"
import { ScreenState } from "@/components/vnb/screen-state"
import { ToolForm } from "@/components/vnb/tool-form"
import { Box, Row } from "@/components/vnb/ui"
import { inr } from "@/lib/format"
import type { AccountRow, MfHolding, MfScheme } from "@/lib/types"
import { read } from "@/lib/vnb"

export default async function MutualFundsPage() {
  const [{ schemes, disclaimer }, { holdings, total_value }, { accounts }] = await Promise.all([
    read<{ schemes: MfScheme[]; disclaimer: string }>("list_mutual_funds"),
    read<{ holdings: MfHolding[]; total_value: number }>("list_mf_holdings"),
    read<{ accounts: AccountRow[] }>("get_account_summary"),
  ])
  return (
    <>
      <ScreenState name="mf_holdings" value={holdings.map((h) => `${h.scheme} ₹${h.value}${h.sip ? ` SIP ₹${h.sip.amount}` : ""}`)} />
      <div className="gv-msg-info">{disclaimer}</div>
      <Box title="VNB Mutual Fund — Schemes (Direct Plan, Growth)">
        <div className="overflow-x-auto">
          <table className="gv-table">
            <thead>
              <tr>
                <th>Scheme</th>
                <th>Category</th>
                <th>Riskometer</th>
                <th className="num">NAV (₹)</th>
                <th className="num">1Y %</th>
                <th className="num">3Y %</th>
                <th className="num">5Y %</th>
                <th className="num">TER %</th>
                <th>Exit load / lock-in</th>
                <th>Min. lumpsum / SIP</th>
                <th>Suitable for</th>
              </tr>
            </thead>
            <tbody>
              {schemes.map((s) => (
                <tr key={s.scheme}>
                  <td>
                    <b>{s.name}</b>
                  </td>
                  <td>{s.category}</td>
                  <td>{s.risk}</td>
                  <td className="num">{s.nav.toFixed(2)}</td>
                  <td className="num">{s.returns["1y"]}</td>
                  <td className="num">{s.returns["3y"]}</td>
                  <td className="num">{s.returns["5y"]}</td>
                  <td className="num">{s.expense_ratio}</td>
                  <td>{s.lock_in ? `Lock-in: ${s.lock_in}` : s.exit_load}</td>
                  <td>
                    ₹{inr(s.min_lumpsum, false)} / ₹{inr(s.min_sip, false)}
                  </td>
                  <td>{s.suits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="gv-note mt-1">Returns are compounded annualised for periods above 1 year. Past performance may or may not be sustained in future.</p>
      </Box>
      <Box title="My Holdings" help={`Current value: ₹${inr(total_value, false)}`}>
        {holdings.length === 0 ? (
          <p className="gv-note">You have no mutual fund holdings.</p>
        ) : (
          <table className="gv-table">
            <thead>
              <tr>
                <th>Folio</th>
                <th>Scheme</th>
                <th className="num">Units</th>
                <th className="num">Invested</th>
                <th className="num">Value</th>
                <th>SIP</th>
                <th className="num">Redeemable now</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.id}>
                  <td>{h.folio}</td>
                  <td>{h.name}</td>
                  <td className="num">{h.units.toFixed(3)}</td>
                  <td className="num">{inr(h.invested)}</td>
                  <td className="num">{inr(h.value)}</td>
                  <td>{h.sip ? `₹${inr(h.sip.amount, false)} on day ${h.sip.day}` : "—"}</td>
                  <td className="num">{inr(h.redeemable_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Box>
      <div className="grid gap-2 lg:grid-cols-2">
        <Box title="Invest — Lumpsum / SIP" id="invest">
          <ToolForm tool="invest_in_mutual_fund" name="Invest in mutual fund" submitLabel="Invest" agree="I have read the Scheme Information Document and understand that investments are subject to market risks.">
            <Row label="Scheme" required>
              <select name="scheme" className="gv-input max-w-full">
                {schemes.map((s) => (
                  <option key={s.scheme} value={s.scheme}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Mode">
              <select name="mode" className="gv-input">
                <option value="lumpsum">Lumpsum (one time)</option>
                <option value="sip">SIP (monthly)</option>
              </select>
            </Row>
            <Row label="Amount (₹)" required>
              <input name="amount" type="number" min={500} className="gv-input w-32" />
            </Row>
            <Row label="SIP date" hint="Only for SIP, 1–28">
              <input name="sip_day" type="number" min={1} max={28} className="gv-input w-16" />
            </Row>
            <Row label="Debit account">
              <AccountSelect accounts={accounts} />
            </Row>
          </ToolForm>
        </Box>
        <Box title="Redeem / Stop SIP" id="redeem">
          <ToolForm tool="redeem_mutual_fund" name="Redeem mutual fund" submitLabel="Redeem" booleans={["stop_sip"]} agree="I understand exit load may apply and ELSS units in lock-in cannot be redeemed.">
            <Row label="Scheme" required>
              <select name="scheme" className="gv-input max-w-full">
                {holdings.map((h) => (
                  <option key={h.id} value={h.scheme}>
                    {h.name} — ₹{inr(h.redeemable_value, false)} redeemable
                  </option>
                ))}
              </select>
            </Row>
            <Row label="Amount (₹)" hint="Blank = all redeemable units">
              <input name="amount" type="number" min={1} className="gv-input w-32" />
            </Row>
            <Row label="SIP">
              <label>
                <input type="checkbox" name="stop_sip" /> Also stop the SIP
              </label>
            </Row>
          </ToolForm>
        </Box>
      </div>
    </>
  )
}
