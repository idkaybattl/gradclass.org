# Email

Transactional mail goes through `django.core.mail`. Every mail key is an
environment variable; `docs/environment.md` lists them with defaults.

## Settings

- `EMAIL_HOST` empty (dev default) selects Django's console backend, so mails
  are printed to the terminal. A host switches to SMTP.
- `DEFAULT_FROM_EMAIL` (`noreply@gradclass.org`) is the `From` address.
- `DEFAULT_REPLY_TO` (`moritz.fechte@gmail.com`) is the `Reply-To` on password
  reset mails, so replies reach a monitored inbox.
- `PASSWORD_RESET_TIMEOUT` is one day.

Production needs SPF/DKIM/DMARC for the sending domain, an accurate
`ALLOWED_HOSTS`, and a proxy that sends `X-Forwarded-Proto: https` (the setting
is already on in `settings.py`), otherwise reset links go out as `http://` or
with the wrong host.

## Which address receives mail

`User.email` is the iServ account record. It is only an *identifier* on the reset
form; mail is never delivered there.

Password reset delivers only to `UserProfile.external_mail`:

- the form accepts the iServ or the external address, case-insensitive;
- every matching active user gets one mail at their own `external_mail`;
- users without an external address are skipped silently, and the response is
  always the generic "sent" page, so account existence does not leak.

There is no verification flow: `external_mail` is trusted from onboarding.

## Admin fallback

Users without an external address ask a `manage_users` holder (superuser) in
person. On the user details overlay, "Reset-Link erzeugen" (POST) shows a
one-time reset link with a copy button. The link is never mailed or logged and
expires after a day; it also stops working once the password changes. Share it
out-of-band (WhatsApp/iServ).

The "Passwort ändern" action stays as a last resort, but it requires handing out
a password; prefer the link.
