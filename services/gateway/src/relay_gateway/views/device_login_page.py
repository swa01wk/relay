"""The page a person opens to approve `relay login`. Values are escaped; nothing is echoed raw."""

from __future__ import annotations

from html import escape

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Relay — connect your terminal</title>
<style>
  :root {{ --bg:#fafafa; --panel:#fff; --line:#e4e4e7; --text:#18181b; --muted:#71717a; --accent:#2563eb; --bad:#b91c1c; --ok:#15803d; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#09090b; --panel:#18181b; --line:#27272a; --text:#fafafa; --muted:#a1a1aa; --accent:#60a5fa; --bad:#f87171; --ok:#4ade80; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:16px; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, sans-serif; }}
  main {{ width:100%; max-width:380px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:24px; }}
  h1 {{ font-size:18px; margin:0 0 4px; }} p {{ margin:0 0 16px; color:var(--muted); }}
  label {{ display:block; font-size:13px; margin:12px 0 4px; }}
  input[type=text], input[type=email], input[type=password] {{ width:100%; font:inherit; color:inherit; background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:8px 10px; }}
  #code {{ font-family:ui-monospace, monospace; letter-spacing:2px; text-transform:uppercase; }}
  .check {{ display:flex; gap:8px; align-items:center; margin:14px 0; font-size:13px; }}
  button {{ width:100%; font:inherit; font-weight:600; color:#fff; background:var(--accent); border:0; border-radius:6px; padding:10px; cursor:pointer; }}
  .bad {{ color:var(--bad); }} .ok {{ color:var(--ok); }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""

_FORM = """<h1>Connect your terminal</h1>
<p>Confirm the code shown by <code>relay login</code>, then sign in.</p>
{message}
<form method="post" action="/v1/auth/device/verify">
  <label for="code">Code from your terminal</label>
  <input id="code" name="code" type="text" value="{code}" autocomplete="off" required>
  <label for="email">Email</label>
  <input id="email" name="email" type="email" value="{email}" autocomplete="email" required>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" minlength="10" required>
  <div class="check"><input id="create" name="create" type="checkbox" value="1"{checked}><label for="create" style="margin:0">I'm new — create my account</label></div>
  <button type="submit">Approve this terminal</button>
</form>
<p style="margin:16px 0 0;font-size:13px"><a href="/v1/auth/forgot-password">Forgot your password?</a></p>"""

_DONE = """<h1 class="ok">Terminal connected</h1>
<p>Signed in as {email}. You can close this tab and return to your terminal.</p>"""


def login_form(*, code: str = "", email: str = "", create: bool = False, error: str = "", info: str = "") -> str:
    message = f'<p class="bad" role="alert">{escape(error)}</p>' if error else ""
    if info:
        message += f'<p class="ok" role="status">{escape(info)}</p>'
    form = _FORM.format(
        message=message, code=escape(code, quote=True), email=escape(email, quote=True),
        checked=" checked" if create else "",
    )  # fmt: skip
    return _PAGE.format(body=form)


def login_done(email: str) -> str:
    return _PAGE.format(body=_DONE.format(email=escape(email)))


def page(body: str) -> str:
    """Any small page in the same frame as the sign-in page (``body`` is trusted markup)."""
    return _PAGE.format(body=body)

