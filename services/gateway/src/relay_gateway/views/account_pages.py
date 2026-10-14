"""Pages for confirming an email and resetting a password. Every value shown is escaped."""

from __future__ import annotations

from html import escape

from relay_gateway.views.device_login_page import page

_INPUT = 'width:100%;margin:4px 0 12px'


def email_confirmed(email: str) -> str:
    return page(
        '<h1 class="ok">Email confirmed</h1>'
        f"<p>{escape(email)} is confirmed. Go back to the sign-in tab and sign in "
        "(leave “I'm new” unticked), or run <code>relay login</code> again.</p>"
    )


def link_problem(message: str) -> str:
    return page(f'<h1>That link didn’t work</h1><p class="bad" role="alert">{escape(message)}</p>'
                '<p><a href="/v1/auth/forgot-password">Request a new password reset link</a></p>')


def forgot_form(*, email: str = "", error: str = "") -> str:
    problem = f'<p class="bad" role="alert">{escape(error)}</p>' if error else ""
    return page(
        "<h1>Reset your password</h1><p>We'll email you a link to choose a new one.</p>"
        f"{problem}"
        '<form method="post" action="/v1/auth/forgot-password">'
        '<label for="email">Email</label>'
        f'<input id="email" name="email" type="email" value="{escape(email, quote=True)}" autocomplete="email" required>'
        '<button type="submit">Email me a link</button></form>'
    )


def forgot_sent(email: str) -> str:
    return page(
        "<h1>Check your inbox</h1>"
        f"<p>If an account exists for {escape(email)}, a reset link is on its way. It expires in 1 hour.</p>"
    )


def reset_form(*, token: str, error: str = "") -> str:
    problem = f'<p class="bad" role="alert">{escape(error)}</p>' if error else ""
    return page(
        "<h1>Choose a new password</h1><p>At least 10 characters. Every signed-in device will be signed out.</p>"
        f"{problem}"
        '<form method="post" action="/v1/auth/reset-password">'
        f'<input type="hidden" name="token" value="{escape(token, quote=True)}">'
        '<label for="password">New password</label>'
        '<input id="password" name="password" type="password" autocomplete="new-password" minlength="10" required>'
        '<button type="submit">Set new password</button></form>'
    )


def reset_done(email: str) -> str:
    return page(
        '<h1 class="ok">Password changed</h1>'
        f"<p>{escape(email)} has a new password and every device was signed out. "
        "Run <code>relay login</code> to sign in again.</p>"
    )
