"use client"

import * as React from "react"

import { Box } from "@/components/vnb/ui"

const RULES: [string, (p: string) => boolean][] = [
  ["8 to 20 characters", (p) => p.length >= 8 && p.length <= 20],
  ["an upper-case letter", (p) => /[A-Z]/.test(p)],
  ["a lower-case letter", (p) => /[a-z]/.test(p)],
  ["a number", (p) => /\d/.test(p)],
  ["a special character (@ # $ % & *)", (p) => /[@#$%&*]/.test(p)],
]

/**
 * Change login / profile password. Site only: passwords never go to the assistant (the SDK skips
 * forms with password fields) and this demo has no real password, so nothing is stored.
 */
export default function ChangePasswordPage() {
  const [message, setMessage] = React.useState<{ ok: boolean; text: string } | null>(null)
  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const next = String(form.get("new_password") ?? "")
    const failed = RULES.filter(([, test]) => !test(next)).map(([label]) => label)
    if (!form.get("old_password")) return setMessage({ ok: false, text: "Enter your current password." })
    if (failed.length) return setMessage({ ok: false, text: `The new password needs ${failed.join(", ")}.` })
    if (next !== form.get("confirm_password")) return setMessage({ ok: false, text: "The new passwords do not match." })
    if (next === form.get("old_password")) return setMessage({ ok: false, text: "The new password must be different from the last 3 passwords." })
    e.currentTarget.reset()
    setMessage({ ok: true, text: `Your ${form.get("which")} password has been changed. Use it from your next login. (Demo: nothing was stored.)` })
  }
  return (
    <Box title="Change Password" help="My Accounts & Profile › Change Password">
      <form onSubmit={submit} aria-label="Change password">
        <table className="gv-form">
          <tbody>
            <tr>
              <td className="gv-label">Password to change</td>
              <td>
                <label className="mr-3">
                  <input type="radio" name="which" value="login" defaultChecked /> Login password
                </label>
                <label>
                  <input type="radio" name="which" value="profile" /> Profile password
                </label>
              </td>
            </tr>
            <tr>
              <td className="gv-label">
                Current password<span className="gv-req"> *</span>
              </td>
              <td>
                <input type="password" name="old_password" className="gv-input w-48" autoComplete="current-password" />
              </td>
            </tr>
            <tr>
              <td className="gv-label">
                New password<span className="gv-req"> *</span>
              </td>
              <td>
                <input type="password" name="new_password" className="gv-input w-48" autoComplete="new-password" />
                <div className="gv-note">Must have {RULES.map(([l]) => l).join(", ")}. Not the same as your last 3 passwords.</div>
              </td>
            </tr>
            <tr>
              <td className="gv-label">
                Confirm new password<span className="gv-req"> *</span>
              </td>
              <td>
                <input type="password" name="confirm_password" className="gv-input w-48" autoComplete="new-password" />
              </td>
            </tr>
          </tbody>
        </table>
        {message && <div className={message.ok ? "gv-msg-ok" : "gv-msg-err"}>{message.text}</div>}
        <div className="mt-1.5 flex gap-2">
          <button className="gv-btn gv-btn-primary">Submit</button>
          <button type="reset" className="gv-btn">
            Reset
          </button>
        </div>
        <p className="gv-note mt-2">For your security, VNB Sahayak cannot see or change your passwords.</p>
      </form>
    </Box>
  )
}
