"""Export the Flask demo as static pages for GitHub Pages."""

import re
from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parent
BASE_PATH = "/DashboardGJ"
PAGES = (
    "dashboard",
    "strategies",
    "strategy_details",
    "subscribe",
    "trading",
    "orders",
    "analytics",
    "settings",
)
ROUTE_PATTERN = re.compile(
    r"(?P<quote>['\"])/(?P<route>"
    + "|".join(PAGES + ("logout",))
    + r")(?P<tail>[/#?]|(?P=quote))"
)


def rewrite_paths(content):
    content = content.replace("/static/", BASE_PATH + "/static/")
    content = content.replace('href="/"', 'href="' + BASE_PATH + '/"')

    def rewrite_route(match):
        tail = match.group("tail")
        slash = "" if tail == "/" else "/"
        return (
            match.group("quote")
            + BASE_PATH
            + "/"
            + match.group("route")
            + slash
            + tail
        )

    return ROUTE_PATTERN.sub(rewrite_route, content)


def export_page(client, route, destination):
    response = client.get(route)
    if response.status_code != 200:
        raise RuntimeError("Could not render " + route)
    html = rewrite_paths(response.get_data(as_text=True))
    html = html.replace(
        'action="' + BASE_PATH + '/logout/" method="post"',
        'action="' + BASE_PATH + '/" method="get"',
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")


def export_login(client):
    response = client.get("/")
    if response.status_code != 200:
        raise RuntimeError("Could not render the login page")
    html = rewrite_paths(response.get_data(as_text=True))
    html = html.replace(
        '<form method="post">',
        '<form method="get" action="' + BASE_PATH + '/">',
    )
    login_script = """<script>
document.querySelector('.login-form form').addEventListener('submit', event => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  if (values.get('email').trim().toLowerCase() === 'student@gjacademy.com' && values.get('password') === 'Demo@123') {
    location.href = '/DashboardGJ/strategies/';
    return;
  }
  let error = document.querySelector('.error-box');
  if (!error) {
    error = document.createElement('div');
    error.className = 'error-box';
    error.setAttribute('role', 'alert');
    form.before(error);
  }
  error.textContent = 'Email or password does not match the demo account.';
});
</script>"""
    html = html.replace("</body>", login_script + "</body>")
    (ROOT / "index.html").write_text(html, encoding="utf-8")


def main():
    app.config["STATIC_EXPORT"] = True
    client = app.test_client()
    export_login(client)
    with client.session_transaction() as session:
        session["student"] = "Alex Morgan"
    for page in PAGES:
        export_page(client, "/" + page, ROOT / page / "index.html")

    app_script = ROOT / "static/js/app.js"
    pages_script = ROOT / "static/js/pages-app.js"
    pages_script.write_text(
        rewrite_paths(app_script.read_text(encoding="utf-8")), encoding="utf-8"
    )
    for page in PAGES:
        page_file = ROOT / page / "index.html"
        html = page_file.read_text(encoding="utf-8")
        html = html.replace("/static/js/app.js", "/static/js/pages-app.js")
        page_file.write_text(html, encoding="utf-8")
    print("Exported GitHub Pages site to " + str(ROOT))


if __name__ == "__main__":
    main()