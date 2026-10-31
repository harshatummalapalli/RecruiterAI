"""LOCAL DEV ONLY — print a browser snippet that logs you into the local app
without Google sign-in (useful when localhost isn't a registered OAuth origin).

It mints a normal, properly-signed session using the app's OWN function and your
own SESSION_SECRET_KEY from .env — the exact session the app creates after Google
verifies you. Nothing here weakens auth; it just lets the owner of the machine log
themselves in locally. Do NOT use on a shared/production host.

Run:  python dev_login.py
Then: copy the printed line, open http://localhost:5173, press F12 -> Console,
      paste it, press Enter. You'll be signed in.
"""

from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value

cookie = create_session_cookie_value("harsha@dayzero.partners")
print("\n--- copy the ONE line below, paste into the browser Console on http://localhost:5173 ---\n")
print(f'document.cookie = "{SESSION_COOKIE_NAME}={cookie}; path=/"; location.reload()')
print("\n--- (then press Enter; the page reloads and you're signed in) ---\n")
