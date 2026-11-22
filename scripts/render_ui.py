#!/usr/bin/env python3
"""Render a Django page or overlay fragment to HTML and a PNG screenshot.

Development helper for checking UI changes. It never writes to the real dev
database: it copies db.sqlite3 to a temporary file, logs in an existing user
from that copy, renders the view with the Django test client, rewrites
STATIC_URL to file:// paths, and screenshots the result with headless Firefox.

Full pages:
    .venv/bin/python scripts/render_ui.py --path / --name home
    .venv/bin/python scripts/render_ui.py --path /events/ --name events

Overlay fragments (rendered inside the real sheet shell):
    .venv/bin/python scripts/render_ui.py --path /events/9/ --overlay --name event-detail
    .venv/bin/python scripts/render_ui.py --path "/events/9/edit/?back=/events/9/" --overlay --name event-edit

Output defaults to .ui-preview/<name>.html and .ui-preview/<name>.png.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Force the sqlite dev configuration before settings are imported, regardless
# of what .env says. The real file is copied below; it is never used directly.
os.environ["ENV"] = "dev"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gradclassorg.settings")

import django  # noqa: E402
from django.conf import settings  # noqa: E402


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 390x844") from exc


def prepare(work_dir: Path) -> None:
    source_db = BASE_DIR / "db.sqlite3"
    if not source_db.is_file():
        raise SystemExit("db.sqlite3 is missing; set up the dev database first.")

    db_copy = work_dir / "render.sqlite3"
    shutil.copy2(source_db, db_copy)
    settings.DATABASES["default"]["NAME"] = str(db_copy)
    # The test client uses "testserver" as the host.
    settings.ALLOWED_HOSTS = ["*"]

    django.setup()

    from django.core.management import call_command

    # Templates use the static manifest, so collect before rendering.
    call_command("collectstatic", interactive=False, verbosity=0)


def build_client(username: str | None):
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    if username:
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise SystemExit(f"No user named {username!r} in the copied database.")
    else:
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if user is None:
        raise SystemExit("No users found in the copied database.")

    client = Client()
    client.force_login(user)
    return client


def rewrite_static(html: str) -> str:
    static_root = Path(settings.STATIC_ROOT).resolve()
    return html.replace(settings.STATIC_URL, f"file://{static_root}/")


ICON_URL_RE = re.compile(r"--icon:\s*url\('file://([^']+)'\)")

# The title card covers whatever page was opened for the whole intro, which
# makes a preview useless. Renders are treated as a repeat view in the tab
# unless --splash asks for the first-load experience.
SPLASH_HIDE = "<style>.splash { display: none; }</style>"


def inline_icon_masks(html: str) -> str:
    """Turn file:// --icon values into data URIs.

    Headless Firefox does not render image-based CSS masks loaded from
    file://, but it does render data-URI masks. The app's icons all mask the
    --icon custom property, so this keeps previews faithful.
    """

    def replace(match: re.Match[str]) -> str:
        try:
            svg = Path(unquote(match.group(1))).read_text(encoding="utf-8")
        except OSError:
            return match.group(0)
        return f"--icon: url('data:image/svg+xml,{quote(svg, safe='')}')"

    return ICON_URL_RE.sub(replace, html)


def render_html(client, path: str, overlay: bool, show_splash: bool = False) -> str:
    kwargs = {"follow": not overlay}
    if overlay:
        kwargs["HTTP_HX_REQUEST"] = "true"

    response = client.get(path, **kwargs)
    html = response.content.decode(response.charset or "utf-8")
    html = inline_icon_masks(rewrite_static(html))
    if not show_splash:
        html = html.replace("</head>", SPLASH_HIDE + "</head>", 1)

    if response.status_code != 200:
        print(f"warning: {path} returned HTTP {response.status_code}", file=sys.stderr)

    if not overlay:
        return html

    shell = client.get("/", follow=True).content.decode(response.charset or "utf-8")
    shell = inline_icon_masks(rewrite_static(shell))
    if not show_splash:
        shell = shell.replace("</head>", SPLASH_HIDE + "</head>", 1)
    shell, opened = re.subn(
        r'class="overlay overlay--sheet"',
        'class="overlay overlay--sheet open"',
        shell,
        count=1,
    )
    shell, injected = re.subn(
        r'(<div[^>]*id="overlay-content"[^>]*>)</div>',
        lambda match: f"{match.group(1)}{html}</div>",
        shell,
        count=1,
    )
    if not opened or not injected:
        raise SystemExit("Could not find the overlay shell in the base page.")
    return shell


def screenshot(html_path: Path, png_path: Path, size: tuple[int, int]) -> None:
    if shutil.which("firefox") is None:
        raise SystemExit("firefox is not installed.")

    profile = Path(tempfile.mkdtemp(prefix="gc-render-profile-"))
    home = Path(tempfile.mkdtemp(prefix="gc-render-home-"))
    runtime = Path(tempfile.mkdtemp(prefix="gc-render-runtime-"))
    profile.chmod(0o700)
    runtime.chmod(0o700)

    env = dict(
        os.environ,
        HOME=str(home),
        XDG_RUNTIME_DIR=str(runtime),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
        MOZ_HEADLESS="1",
        MOZ_WEBRENDER="0",
        LIBGL_ALWAYS_SOFTWARE="1",
        MOZ_CRASHREPORTER_DISABLE="1",
    )

    subprocess.run(
        [
            "firefox",
            "--no-remote",
            "--new-instance",
            "-profile",
            str(profile),
            "--headless",
            f"--window-size={size[0]},{size[1]}",
            "--screenshot",
            str(png_path),
            html_path.as_uri(),
        ],
        env=env,
        check=True,
        timeout=60,
    )
    if not png_path.is_file():
        raise SystemExit("firefox did not write the screenshot.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--path", required=True, help="URL path to render")
    parser.add_argument("--name", help="output name (default: derived from path)")
    parser.add_argument(
        "--user", help="username to log in as (default: first superuser)"
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="render the response inside the open bottom sheet",
    )
    parser.add_argument(
        "--splash",
        action="store_true",
        help="keep the title card, which is hidden in renders by default",
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        default=(390, 844),
        help="viewport WIDTHxHEIGHT (default: 390x844)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BASE_DIR / ".ui-preview",
        help="output directory (default: .ui-preview)",
    )
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="gc-render-db-"))
    prepare(work_dir)
    client = build_client(args.user)
    html = render_html(client, args.path, args.overlay, args.splash)

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or re.sub(r"[^a-z0-9]+", "-", args.path.strip("/").lower()).strip(
        "-"
    )
    html_path = out_dir / f"{stem or 'page'}.html"
    png_path = out_dir / f"{stem or 'page'}.png"
    html_path.write_text(html, encoding="utf-8")

    screenshot(html_path, png_path, args.size)
    print(png_path)


if __name__ == "__main__":
    main()
