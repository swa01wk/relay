"use client"

import * as React from "react"
import { useRouter } from "next/navigation"

import { Box } from "@/components/vnb/ui"

const CAPTCHA = "7xK2pQ"

/**
 * The login page, with everything a PSU bank login has (virtual keyboard, captcha, a wall of
 * instructions). This demo has no real sign-in: the details are prefilled and lead to the demo customer.
 */
export default function LoginPage() {
  const router = useRouter()
  const [error, setError] = React.useState<string | null>(null)
  const [vk, setVk] = React.useState(false)

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    if (String(form.get("captcha")).trim() !== CAPTCHA) return setError("Please enter the correct text shown in the image.")
    if (!form.get("terms")) return setError("Please read and agree to the terms before login.")
    router.push("/home")
  }

  return (
    <div className="grid gap-3 px-3 py-3 lg:grid-cols-[1fr_1.2fr]">
      <Box title="Login to Internet Banking (Personal Banking)" help="* Mandatory fields">
        <form onSubmit={submit} aria-label="Login">
          <table className="gv-form">
            <tbody>
              <tr>
                <td className="gv-label">
                  Username<span className="gv-req"> *</span>
                </td>
                <td>
                  <input name="username" className="gv-input w-48" defaultValue="rcverma79" autoComplete="username" />
                </td>
              </tr>
              <tr>
                <td className="gv-label">
                  Password<span className="gv-req"> *</span>
                </td>
                <td>
                  <input name="password" type="password" className="gv-input w-48" defaultValue="demo-password" autoComplete="current-password" />
                  <label className="ml-2 text-[11px]">
                    <input type="checkbox" checked={vk} onChange={(e) => setVk(e.target.checked)} /> Enable Virtual Keyboard
                  </label>
                  {vk && (
                    <div className="mt-1 grid w-72 grid-cols-10 gap-0.5 border border-[#999] bg-[#eee] p-1 text-center font-mono text-[11px]">
                      {"7194382065qwertyuiopasdfghjklzxcvbnm@#$%".split("").map((c) => (
                        <span key={c} className="border border-[#aaa] bg-white">
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
              <tr>
                <td className="gv-label">
                  Enter the text as shown in the image<span className="gv-req"> *</span>
                </td>
                <td>
                  <span
                    className="mr-2 inline-block select-none bg-[repeating-linear-gradient(45deg,#ddd,#ddd_3px,#f6f6f6_3px,#f6f6f6_6px)] px-3 py-0.5 font-mono text-[16px] italic tracking-[0.3em] text-[#5a1a1a] line-through decoration-[#888]"
                    aria-label={`Captcha ${CAPTCHA.split("").join(" ")}`}
                  >
                    {CAPTCHA}
                  </span>
                  <input name="captcha" className="gv-input w-28" defaultValue={CAPTCHA} />
                  <div className="gv-note">Demo: the captcha is filled in for you. ↻ Refresh captcha · 🔊 Audio captcha</div>
                </td>
              </tr>
            </tbody>
          </table>
          <label className="mt-1.5 flex items-start gap-1.5">
            <input type="checkbox" name="terms" defaultChecked />
            <span className="gv-note">I have read the security guidelines and the terms and conditions of Internet Banking and agree to them.</span>
          </label>
          {error && <div className="gv-msg-err">{error}</div>}
          <div className="mt-2 flex gap-2">
            <button className="gv-btn gv-btn-primary">Login</button>
            <button type="reset" className="gv-btn">
              Reset
            </button>
          </div>
          <p className="gv-note mt-2">New User? Register here · Forgot Login Password · Forgot Username · Unlock User (Self)</p>
        </form>
      </Box>
      <Box title="Dear Customer,">
        <ul className="list-disc space-y-1 pl-5 text-[11px]">
          <li>Mandatory fields are marked with an asterisk (*).</li>
          <li>Do not provide your username and password anywhere other than in this page.</li>
          <li>Your user name and password are highly confidential. Never part with them. VNB will never ask for this information.</li>
          <li>Always visit this page directly. Do not click on links in e-mails or SMS to reach this page.</li>
          <li>Ensure the address bar shows https and the padlock icon before entering credentials.</li>
          <li>Please change your password at least once in 90 days. The password should contain at least 8 characters with a capital letter, a number and a special character.</li>
          <li>Use the Virtual Keyboard on shared computers (cyber cafés) to protect against key-loggers.</li>
          <li>Your session will expire automatically after 5 minutes of inactivity.</li>
          <li>Do not use the browser&apos;s Back / Refresh buttons during a transaction; it may result in a duplicate transaction.</li>
          <li>Report any unauthorised transaction immediately to 1800 11 2244 or through &quot;Register Complaint of Unauthorised Transaction&quot;.</li>
          <li>Login with your username and password, then authorise with the OTP sent to your registered mobile number (demo: no OTP).</li>
        </ul>
      </Box>
    </div>
  )
}
