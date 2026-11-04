"""End-to-end check of a deployed app, through its real forms.

    python3 deploy/railway/e2e.py https://carobon-credit-production.up.railway.app \
        [--legacy https://web-production-c782e.up.railway.app]

Submits each form the way a browser with JavaScript off does, so every step
runs the same server actions, proxy, rewrites, row-level security and engine
call a person would. Stdlib only.

It writes to the database it tests: each run signs up a new
`e2e-<random>@example.com` account that owns an "E2E Farmers Collective" with
one project and one farm. Run it against production only when that is fine.
"""
import argparse
import http.cookiejar
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from html.parser import HTMLParser

ap = argparse.ArgumentParser()
ap.add_argument("base", help="the canonical site, e.g. https://carobon-credit-production.up.railway.app")
ap.add_argument("--legacy", action="append", default=[], help="an old address that must redirect to the canonical one")
args = ap.parse_args()
BASE = args.base.rstrip("/")
HOST = urllib.parse.urlparse(BASE).netloc


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms, self.cur = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.cur = {"fields": [], "names": []}
            self.forms.append(self.cur)
        elif tag in ("input", "button", "select", "textarea") and self.cur is not None and a.get("name"):
            self.cur["names"].append(a["name"])
            if a.get("type") == "hidden":
                self.cur["fields"].append((a["name"], a.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "form":
            self.cur = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def raw(url, data=None, headers=None, retry=True):
    headers = dict(headers or {})
    if data is not None:
        headers["Origin"] = BASE  # as a browser sends with every form post
    try:
        resp = opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=90)
        return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")
    except ConnectionResetError:
        if not retry or data is not None:
            raise
        return raw(url, data, headers, retry=False)


def follow(path, data=None, headers=None, hops=6):
    """Follow redirects, failing loudly if one leaves the canonical site."""
    for _ in range(hops):
        status, h, body = raw(BASE + path, data, headers)
        if status in (301, 302, 303, 307, 308):
            loc = urllib.parse.urlparse(urllib.parse.urljoin(BASE + path, h["Location"]))
            if loc.netloc != HOST:
                raise AssertionError(f"redirect left {HOST}: {h['Location']}")
            path = loc._replace(scheme="", netloc="").geturl()
            data, headers = None, None
            continue
        return status, path, body
    raise RuntimeError("too many redirects")


def multipart(fields):
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields]
    return ("".join(parts) + f"--{b}--\r\n").encode(), {"Content-Type": f"multipart/form-data; boundary={b}"}


def submit(page, must_have, values):
    """Fill the form on `page` that has a field named `must_have`, submit it, follow redirects."""
    _, _, html = follow(page)
    p = Forms()
    p.feed(html)
    form = next(f for f in p.forms if must_have in f["names"])
    hidden = [(k, v) for k, v in form["fields"] if k not in values]
    body, headers = multipart(hidden + list(values.items()))
    return follow(page, body, headers)


def notices(body):
    return " | ".join(re.findall(r'text-text/90">([^<]{0,240})', body))


ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail and not cond else ""))


# --- the address --------------------------------------------------------------

for legacy in args.legacy:
    status, h, _ = raw(legacy.rstrip("/") + "/app/farms?project=x")
    check(f"{urllib.parse.urlparse(legacy).netloc} redirects permanently to the same path here",
          status == 308 and h.get("Location") == f"{BASE}/app/farms?project=x", f"{status} {h.get('Location')}")

status, h, _ = raw(BASE + "/app")
check("signed out: /app redirects to this site's /login", status in (302, 303, 307) and
      urllib.parse.urlparse(urllib.parse.urljoin(BASE, h["Location"])).netloc == HOST
      and "/login" in h["Location"], f"{status} {h.get('Location')}")

status, h, _ = raw(BASE + "/auth/callback?error_description=Email%20link%20is%20invalid%20or%20has%20expired")
check("an expired email link lands on this site's login with the reason",
      status in (302, 307) and h["Location"].startswith(f"{BASE}/login?error="), f"{status} {h.get('Location')}")

status, _, body = raw(BASE + "/auth/v1/health")
check("auth service answers through the site", status == 200, str(status))

# --- accounts -----------------------------------------------------------------

email = f"e2e-{secrets.token_hex(4)}@example.com"
password = "Correct horse battery 9"

status, path, body = submit("/signup", "confirm_password",
                            {"full_name": "E2E Tester", "email": email, "password": password, "confirm_password": "mismatch!!"})
check("signup refuses mismatched passwords", "do not match" in body, path)

status, path, body = submit("/signup", "confirm_password",
                            {"full_name": "E2E Tester", "email": email, "password": password, "confirm_password": password})
check("signup lands on onboarding", path == "/onboarding" and "Set up your organisation" in body, f"{status} {path}")

status, path, body = submit("/onboarding", "kind", {"name": "E2E Farmers Collective", "kind": "aggregator", "country": "India"})
check("create organisation lands on the dashboard", path == "/app" and "E2E Farmers Collective" in body, f"{status} {path}")

status, path, _ = follow("/login")
check("signed in: /login sends you on to /app", path == "/app", path)

status, path, body = follow("/app/profile")
check("profile shows the account, organisation and role",
      status == 200 and email in body and "E2E Farmers Collective" in body and "Owner" in body, f"{status} {path}")

status, path, body = submit("/app/profile", "phone", {"full_name": "E2E Renamed", "phone": "+91 98765 43210"})
check("profile saves", "Profile saved" in body, notices(body))
status, path, body = follow("/app/profile")
check("saved name and phone come back", "E2E Renamed" in body and "+91 98765 43210" in body)

status, path, body = submit("/app/profile", "current_password",
                            {"current_password": "wrong password!!", "password": "Another long pass 1",
                             "confirm_password": "Another long pass 1"})
check("password change needs the current password", "current password is not right" in body, notices(body))

status, path, body = submit("/app/profile", "confirm_email", {"confirm_email": "not-my@email.com"})
check("closing the account needs the email typed exactly", "Type your email address exactly" in body, notices(body))
status, path, body = submit("/app/profile", "confirm_email", {"confirm_email": email})
check("the last owner cannot close their account", "only owner of E2E Farmers Collective" in body, notices(body))

status, path, body = submit("/app/settings", "email", {"email": "colleague@example.com", "role": "analyst"})
check("an owner creates an invitation link on this site", f"{BASE}/invite/" in body, notices(body))

# --- the product path: project -> farm -> estimate from the engine ------------

status, path, body = submit("/app/projects/new", "pathway",
                            {"name": "E2E Nyeri shade coffee", "pathway": "agroforestry", "country": "Kenya", "region": "Nyeri"})
check("create project", path.startswith("/app/projects/") and status == 200, f"{status} {path}")
project_id = path.rstrip("/").split("/")[-1]

boundary = ('{"type":"Polygon","coordinates":[[[36.9470,-0.4210],[36.9490,-0.4210],'
            '[36.9490,-0.4228],[36.9470,-0.4228],[36.9470,-0.4210]]]}')
status, path, body = submit("/app/farms/new", "boundary", {
    "name": "E2E Wanjiru shade plot", "project_id": project_id, "enrolled_on": "2025-03-01",
    "crop": "Coffee under shade", "practice": "shade_trees", "farmer_id": "new",
    "new_farmer_name": "Wanjiru E2E", "consent_on": "2025-02-20", "consent_reference": "E2E-CONSENT-1",
    "tenure": "owned_title", "tenure_reference": "NYERI/E2E/1", "species": "Grevillea robusta, Cordia africana",
    "stems_planted": "120", "boundary": boundary, "source": "drawn"})
check("enrol a farm with a new farmer", path.startswith("/app/farms/") and "created=1" in path, f"{status} {path} {notices(body)}")
farm_id = path.split("/app/farms/")[1].split("?")[0]

status, path, body = submit(f"/app/farms/{farm_id}", "farm_id", {"farm_id": farm_id})
check("the engine estimates the farm", "Estimate updated" in body, notices(body))

# --- leaving and coming back --------------------------------------------------

_, _, html = follow("/app")
p = Forms()
p.feed(html)
signout = next(f for f in p.forms if all(n.startswith("$ACTION") for n in f["names"]))
body, headers = multipart(signout["fields"])
status, path, _ = follow("/app", body, headers)
check("sign out lands on /login", path.startswith("/login"), path)
status, path, _ = follow("/app/profile")
check("after signing out, the profile needs a login again", path.startswith("/login"), path)

status, path, body = submit("/forgot", "email", {"email": email})
check("password reset reports honestly whether email can be sent",
      "reset link is on its way" in body or "Email could not be sent" in body, notices(body))

status, path, body = submit("/login", "password", {"email": email, "password": "wrong password here"})
check("login refuses a wrong password", "Invalid login credentials" in body, notices(body))
status, path, body = submit("/login", "password", {"email": email, "password": password})
check("login lands back on the dashboard", path == "/app" and "E2E Farmers Collective" in body, path)

print("ALL PASSED" if ok else "SOME CHECKS FAILED")
print("test account:", email)
sys.exit(0 if ok else 1)
