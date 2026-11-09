#!/usr/bin/env python3
"""
Fred Raket - site tool
======================

Klein lokaal programma om de website fredraket.be up-to-date te houden.

  * foto's erin slepen  -> worden automatisch verkleind en gecomprimeerd
  * titel + tekstje erbij -> er komt een nieuwe tegel bij (Fotografie of Home)
  * extra foto's toevoegen aan een bestaand album
  * lokaal bekijken en met een klik naar GitHub pushen

Gebruikt enkel wat standaard op een Mac staat: python3, git en `sips`
(de ingebouwde beeldconverter van macOS). Op andere systemen valt het
terug op Pillow als dat geinstalleerd is.

Starten: dubbelklik op "Site Tool.command" (of: python3 site_tool.py)
"""

import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# --------------------------------------------------------------------------
# Instellingen
# --------------------------------------------------------------------------
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOL_DIR)          # de map van de website (1 niveau hoger)
PORT = 8765
VERSION = 4

FULL_PX, FULL_Q = 2000, 0.85    # grote foto (lightbox): langste zijde, JPEG-kwaliteit
THUMB_PX, THUMB_Q = 700, 0.8    # kleine foto in het raster
TILE_W = 800                    # breedte van de tegelfoto (hoogte volgt bestaande tegels)
GRID_RATIO = 1.25               # verhouding (breedte/hoogte) van een vakje in het fotoraster
DEFAULT_TILE_RATIO = 326 / 353  # hoogte/breedte als er geen bestaande tegel is

M_TILES_BEGIN = "<!-- TOOL:TEGELS-BEGIN -->"
M_TILES_END = "<!-- TOOL:TEGELS-EINDE -->"
M_PHOTOS_END = "<!-- TOOL:FOTOS-EINDE -->"
M_MENU_END = "<!-- TOOL:MENU-EINDE -->"

STAGING = tempfile.mkdtemp(prefix="fredraket-")
USE_SIPS = sys.platform == "darwin" and shutil.which("sips") is not None

# --------------------------------------------------------------------------
# HTML-sjablonen (dezelfde opbouw als de rest van de site)
# --------------------------------------------------------------------------
def esc(s):
    return html.escape(s or "", quote=True)


FOOTER = """
            <footer id="footer">
                <div class="inner">
                    <section>
                        <h2>Contact</h2>
                        <a href="mailto:fred@grom.gr" class="contact-link">fred@grom.gr</a>
                    </section>
                    <section>
                        <h2>Volg Fred Raket</h2>
                        <ul class="social-icons">
                            <li><a href="https://www.youtube.com/@fredraket" target="_blank" rel="noopener" class="icon brands fa-youtube"><span class="label">YouTube</span></a></li>
                            <li><a href="https://www.instagram.com/fred.raket.fpv/" target="_blank" rel="noopener" class="icon brands fa-instagram"><span class="label">Instagram</span></a></li>
                            <li><a href="mailto:fred@grom.gr" class="icon solid fa-envelope"><span class="label">E-mail</span></a></li>
                        </ul>
                    </section>
                    <div class="copyright">
                        &copy; Fred Raket. Alle rechten voorbehouden. Alle foto's, video's en teksten op deze site zijn eigendom van Fred Raket en mogen niet zonder schriftelijke toestemming gebruikt worden.<br />
                        Design: <a href="https://html5up.net" target="_blank" rel="noopener">HTML5 UP</a>
                    </div>
                </div>
            </footer>
        </div>
"""

SCRIPTS = """
        <script src="assets/js/jquery.min.js"></script>
        <script src="assets/js/browser.min.js"></script>
        <script src="assets/js/breakpoints.min.js"></script>
        <script src="assets/js/util.js"></script>
        <script src="assets/js/main.js"></script>
"""

GALLERY_CSS = '        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/magnific-popup.js/1.1.0/magnific-popup.min.css" />\n'

GALLERY_JS = """        <script src="https://cdnjs.cloudflare.com/ajax/libs/magnific-popup.js/1.1.0/jquery.magnific-popup.min.js"></script>
        <script>
            $(function() {
                $('.gallery').magnificPopup({
                    delegate: 'a',
                    type: 'image',
                    gallery: { enabled: true, navigateByImgClick: true, preload: [0, 1] }
                });
            });
        </script>
"""

DEFAULT_MENU = """
            <nav id="menu">
                <h2>Menu</h2>
                <ul>
                    <li><a href="index.html">Home</a></li>
                    <li><a href="over-mij.html">Over mij</a></li>
                </ul>
                <h3 class="menu-kop">Projecten</h3>
                <ul>
                    <li><a href="fpv.html">FPV</a></li>
                    <li><a href="Fotografie.html">Fotografie</a></li>
                    <li><a href="geluid.html">Geluid</a></li>
                    <li><a href="drone.html">Reguliere drone</a></li>
                    <li><a href="set-bouw.html">Set bouw</a></li>
                    <li><a href="maker.html">Maker</a></li>
                    """ + M_MENU_END + """
                </ul>
                <h3 class="menu-kop">Volg mij</h3>
                <ul>
                    <li><a href="https://www.youtube.com/@fredraket" target="_blank" rel="noopener">YouTube</a></li>
                    <li><a href="https://www.instagram.com/fred.raket.fpv/" target="_blank" rel="noopener">Instagram</a></li>
                </ul>
            </nav>
"""


def current_menu():
    """Neem het menu over van index.html, zodat nieuwe pagina's altijd hetzelfde menu hebben."""
    try:
        with open(os.path.join(REPO, "index.html"), encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"\n[ \t]*<nav id=\"menu\">.*?</nav>\n", text, re.S)
        if m:
            return m.group(0)
    except OSError:
        pass
    return DEFAULT_MENU


def page(title, description, body_class, header, main, gallery=False, menu=None):
    return (
        '<!DOCTYPE HTML>\n<html lang="nl">\n    <head>\n'
        f"        <title>{esc(title)}</title>\n"
        '        <meta charset="utf-8" />\n'
        '        <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f'        <meta name="description" content="{esc(description)}" />\n'
        '        <link rel="stylesheet" href="assets/css/main.css" />\n'
        '        <noscript><link rel="stylesheet" href="assets/css/noscript.css" /></noscript>\n'
        + (GALLERY_CSS if gallery else "")
        + '        <link rel="stylesheet" href="assets/css/fred.css" />\n'
        "    </head>\n"
        f'    <body class="is-preload {body_class}">\n'
        '        <div id="wrapper">\n'
        + header
        + (menu if menu is not None else current_menu())
        + main
        + FOOTER
        + SCRIPTS
        + (GALLERY_JS if gallery else "")
        + "    </body>\n</html>\n"
    )


def album_header(back_href, back_label):
    return f"""
            <header id="header">
                <div class="inner">
                    <a href="index.html" class="logo">
                        <span class="symbol"><img src="images/logo.png" alt="Fred Raket" /></span>
                    </a>
                    <a href="{esc(back_href)}" class="back-button">&larr; Terug naar {esc(back_label)}</a>
                    <nav><ul><li><a href="#menu">Menu</a></li></ul></nav>
                </div>
            </header>
"""


def photo_item(full, thumb, alt, pos="", indent=" " * 24):
    style = f' style="object-position: {esc(pos)}"' if pos else ""
    return f'{indent}<a href="{esc(full)}"><img src="{esc(thumb)}" alt="{esc(alt)}"{style} loading="lazy" /></a>'


def album_page(title, intro, photos, back_href="Fotografie.html", back_label="Fotografie", menu=None):
    """photos = lijst van (groot, klein, alt[, object-position])"""
    items = "\n".join(photo_item(*p) for p in photos)
    paras = [p.strip() for p in re.split(r"\n\s*\n", intro or "") if p.strip()]
    intro_html = "".join(f"\n                    <p>{esc(p)}</p>" for p in paras)
    if paras:
        intro_html = '\n                    <div class="album-intro">' + intro_html.replace("\n                    <p>", "\n                        <p>") + "\n                    </div>"
    main = f"""
            <div id="main">
                <div class="inner">
                    <h1>{esc(title)}</h1>{intro_html}
                    <div class="photo-grid gallery">
{items + chr(10) if items else ""}                        {M_PHOTOS_END}
                    </div>
                </div>
            </div>
"""
    desc = (paras[0][:155] if paras else f"{title} - Fred Raket.")
    return page(f"{title} - Fred Raket", desc, "page-album", album_header(back_href, back_label), main, gallery=True, menu=menu)


def tile(style_n, img, href, title, subtitle=""):
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    return (f'<article class="style{style_n}"><span class="image"><img src="{esc(img)}" alt="" /></span>'
            f'<a href="{esc(href)}"><h2>{esc(title)}</h2>{sub}</a></article>')


# --------------------------------------------------------------------------
# Hulpfuncties
# --------------------------------------------------------------------------
def slugify(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "album"


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


def write(rel, text):
    with open(os.path.join(REPO, rel), "w", encoding="utf-8") as f:
        f.write(text)


def insert_line(text, marker, snippet, after=False):
    """Zet `snippet` op een eigen regel voor (of na) de regel met `marker`, met dezelfde inspringing."""
    idx = text.find(marker)
    if idx < 0:
        raise ValueError(f"Markering {marker} niet gevonden")
    line_start = text.rfind("\n", 0, idx) + 1
    indent = re.match(r"[ \t]*", text[line_start:]).group(0)
    if after:
        line_end = text.find("\n", idx)
        line_end = len(text) if line_end < 0 else line_end
        return text[:line_end] + "\n" + indent + snippet + text[line_end:]
    return text[:line_start] + indent + snippet + "\n" + text[line_start:]


def image_size(path):
    if USE_SIPS:
        out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                             capture_output=True, text=True).stdout
        w = int(re.search(r"pixelWidth:\s*(\d+)", out).group(1))
        h = int(re.search(r"pixelHeight:\s*(\d+)", out).group(1))
        return w, h
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return im.size


def run_sips(args):
    r = subprocess.run(["sips"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())


def make_jpeg(src, dst, max_px, quality):
    """Verklein tot max_px (langste zijde) en sla op als JPEG."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if USE_SIPS:
        w, h = image_size(src)
        args = ["-s", "format", "jpeg", "-s", "formatOptions", str(quality)]
        if max(w, h) > max_px:
            args += ["-Z", str(max_px)]
        run_sips(args + [src, "--out", dst])
        return
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_px, max_px), Image.LANCZOS)
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)


def tile_ratio(page_rel):
    """Lees de verhouding van de eerste bestaande tegelfoto, zodat nieuwe tegels netjes passen."""
    try:
        text = read(page_rel)
        sec = text[text.find(M_TILES_BEGIN):text.find(M_TILES_END)]
        for src in re.findall(r'<span class="image"><img src="([^"]+)"', sec):
            p = os.path.join(REPO, unquote(src))
            if os.path.exists(p):
                w, h = image_size(p)
                return h / w
    except Exception:
        pass
    return DEFAULT_TILE_RATIO


def next_style(text):
    sec = text[text.find(M_TILES_BEGIN):text.find(M_TILES_END)]
    n = len(re.findall(r'<article class="style\d', sec))
    return n % 6 + 1


def next_photo_number(folder, prefix):
    nums = [0]
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = re.match(re.escape(prefix) + r"-(\d+)\.jpg$", name)
            if m:
                nums.append(int(m.group(1)))
    return max(nums) + 1


POS_RE = re.compile(r"^\d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$")


def save_staged(sid, rel):
    src = staged_path(sid)
    with open(src, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            raise ValueError("geen geldige JPEG ontvangen")
    dst = os.path.join(REPO, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def store_photos(photos, img_dir_rel, prefix, alt_base):
    """photos = lijst van {full, thumb, pos}: al verkleind en gedraaid door de browser."""
    n = next_photo_number(os.path.join(REPO, img_dir_rel), prefix)
    items = []
    for p in photos:
        name = f"{prefix}-{n:02d}.jpg"
        full_rel, thumb_rel = f"{img_dir_rel}/{name}", f"{img_dir_rel}/thumbs/{name}"
        save_staged(p["full"], full_rel)
        save_staged(p["thumb"], thumb_rel)
        pos = (p.get("pos") or "").strip()
        if not POS_RE.match(pos) or pos.replace(".0", "") == "50% 50%":
            pos = ""
        items.append((full_rel, thumb_rel, f"{alt_base} - foto {n}", pos))
        n += 1
    return items


STAGED_NAMES = {}


def staged_path(sid):
    if not re.fullmatch(r"[0-9a-f]{32}", sid or ""):
        raise ValueError("ongeldige upload")
    return os.path.join(STAGING, sid)


def list_albums():
    albums = []
    for name in sorted(os.listdir(REPO)):
        if not name.endswith(".html"):
            continue
        try:
            text = read(name)
        except OSError:
            continue
        if M_PHOTOS_END in text:
            m = re.search(r"<h1>(.*?)</h1>", text, re.S)
            title = html.unescape(m.group(1).strip()) if m else name
            count = len(re.findall(r"<a href=[^>]*><img ", text[text.find("photo-grid"):]))
            albums.append({"page": name, "title": title, "count": count})
    return albums


# --------------------------------------------------------------------------
# Acties
# --------------------------------------------------------------------------
def action_create(data):
    where = data.get("where", "fotografie")
    title = (data.get("title") or "").strip()
    subtitle = (data.get("subtitle") or "").strip()
    intro = (data.get("intro") or "").strip()
    photos = data.get("photos") or []
    tile_id = data.get("tile")
    position = data.get("position", "top")
    if not title:
        raise ValueError("Geef een titel op.")
    if not photos or not tile_id:
        raise ValueError("Sleep minstens een foto in het vak.")

    slug = slugify(title)
    page_rel = f"{slug}.html"
    if os.path.exists(os.path.join(REPO, page_rel)):
        raise ValueError(f"Er bestaat al een pagina {page_rel}. Kies een andere titel.")

    parent_rel = "index.html" if where == "home" else "Fotografie.html"
    back_label = "Home" if where == "home" else "Fotografie"
    img_dir = f"images/{slug}"

    items = store_photos(photos, img_dir, slug, title)

    # tegelfoto (al bijgesneden in de browser)
    tile_rel = f"{img_dir}/tegel.jpg"
    save_staged(tile_id, tile_rel)

    # pagina
    write(page_rel, album_page(title, intro, items, parent_rel, back_label))

    # tegel op Fotografie- of homepagina
    parent = read(parent_rel)
    snippet = tile(next_style(parent), tile_rel, page_rel, title, subtitle)
    if position == "bottom":
        parent = insert_line(parent, M_TILES_END, snippet)
    else:
        parent = insert_line(parent, M_TILES_BEGIN, snippet, after=True)
    write(parent_rel, parent)

    # menu-item voor een nieuwe rubriek op de homepagina
    if where == "home" and data.get("menu", True):
        add_menu_item(page_rel, title)

    return {"ok": True, "page": page_rel, "count": len(items), "errors": []}


def add_menu_item(href, label):
    li = f'<li><a href="{esc(href)}">{esc(label)}</a></li>'
    for name in os.listdir(REPO):
        if name.endswith(".html"):
            text = read(name)
            if M_MENU_END in text and f'href="{href}"' not in text.split(M_MENU_END)[0][-2000:]:
                write(name, insert_line(text, M_MENU_END, li))


def action_add(data):
    page_rel = os.path.basename(data.get("page") or "")
    photos = data.get("photos") or []
    if not page_rel or not os.path.exists(os.path.join(REPO, page_rel)):
        raise ValueError("Kies een album.")
    if not photos:
        raise ValueError("Sleep minstens een foto in het vak.")
    text = read(page_rel)
    m = re.search(r"<h1>(.*?)</h1>", text, re.S)
    title = html.unescape(m.group(1).strip()) if m else page_rel
    stem = slugify(page_rel[:-5])
    items = store_photos(photos, f"images/{stem}", stem, title)
    for full, thumb, alt, pos in items:
        text = insert_line(text, M_PHOTOS_END, photo_item(full, thumb, alt, pos, indent=""))
    write(page_rel, text)
    return {"ok": True, "page": page_rel, "count": len(items), "errors": []}


# ---------- bestaande albums bewerken ----------
GRID_OPEN = '<div class="photo-grid gallery">'


def clean_pos(pos):
    pos = (pos or "").strip()
    return "" if not POS_RE.match(pos) or pos.replace(".0", "") == "50% 50%" else pos


def find_tile(page_rel):
    pat = (r'<article class="style(\d)"><span class="image"><img src="([^"]*)" alt="" /></span>'
           r'<a href="' + re.escape(page_rel) + r'"><h2>(.*?)</h2>(?:<p>(.*?)</p>)?</a></article>')
    for parent in ("Fotografie.html", "index.html"):
        if not os.path.exists(os.path.join(REPO, parent)):
            continue
        m = re.search(pat, read(parent))
        if m:
            return {"parent": parent, "style": int(m.group(1)), "img": html.unescape(m.group(2)),
                    "title": html.unescape(m.group(3)), "subtitle": html.unescape(m.group(4) or ""),
                    "match": m.group(0)}
    return None


def album_page_rel(name):
    page_rel = os.path.basename(name or "")
    if not page_rel.endswith(".html") or not os.path.exists(os.path.join(REPO, page_rel)):
        raise ValueError("Album niet gevonden.")
    text = read(page_rel)
    if M_PHOTOS_END not in text or GRID_OPEN not in text:
        raise ValueError("Deze pagina is geen album dat de tool kan bewerken.")
    return page_rel, text


def action_album_get(page):
    page_rel, text = album_page_rel(page)
    h1 = re.search(r"<h1>(.*?)</h1>", text, re.S)
    g = text.find(GRID_OPEN)
    intro_html = text[h1.end():g]
    paras = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<p>(.*?)</p>", intro_html, re.S)]
    grid = text[g:text.find(M_PHOTOS_END)]
    photos = []
    for a in re.finditer(r'<a href="([^"]*)"><img ([^>]*?)/?>\s*</a>', grid):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', a.group(2)))
        pm = re.search(r"object-position:\s*([^;\"]+)", attrs.get("style", ""))
        photos.append({"full": html.unescape(a.group(1)), "thumb": html.unescape(attrs.get("src", "")),
                       "pos": pm.group(1).strip() if pm else ""})
    t = find_tile(page_rel)
    tile = None
    if t:
        tile = {k: t[k] for k in ("parent", "img", "subtitle")}
        tile["ratio"] = tile_ratio(t["parent"])
    return {"page": page_rel, "title": html.unescape(h1.group(1).strip()),
            "intro": "\n\n".join(x for x in paras if x), "photos": photos, "tile": tile}


def action_album_save(d):
    page_rel, text = album_page_rel(d.get("page"))
    old = action_album_get(page_rel)
    known = {(p["full"], p["thumb"]) for p in old["photos"]}
    title = (d.get("title") or "").strip() or old["title"]
    intro = (d.get("intro") or "").strip()
    stem = slugify(page_rel[:-5])
    img_dir = f"images/{stem}"
    n = next_photo_number(os.path.join(REPO, img_dir), stem)

    lines = []
    for i, p in enumerate(d.get("photos") or [], 1):
        if p.get("newFull"):
            name = f"{stem}-{n:02d}.jpg"
            full, thumb = f"{img_dir}/{name}", f"{img_dir}/thumbs/{name}"
            save_staged(p["newFull"], full)
            save_staged(p["newThumb"], thumb)
            n += 1
        else:
            full, thumb = p.get("full"), p.get("thumb")
            if (full, thumb) not in known:
                raise ValueError("Onbekende foto in de lijst.")
        lines.append(photo_item(full, thumb, f"{title} - foto {i}", clean_pos(p.get("pos"))))

    # titel
    text = re.sub(r"<h1>.*?</h1>", lambda m: f"<h1>{esc(title)}</h1>", text, count=1, flags=re.S)
    text = re.sub(r"<title>.*?</title>", lambda m: f"<title>{esc(title)} - Fred Raket</title>", text, count=1, flags=re.S)
    # intro
    paras = [x.strip() for x in re.split(r"\n\s*\n", intro) if x.strip()]
    intro_html = ""
    if paras:
        intro_html = '\n                    <div class="album-intro">' + "".join(
            f"\n                        <p>{esc(x)}</p>" for x in paras) + "\n                    </div>"
        text = re.sub(r'<meta name="description" content="[^"]*" />',
                      lambda m: f'<meta name="description" content="{esc(paras[0][:155])}" />', text, count=1)
    h1_end = text.find("</h1>") + len("</h1>")
    g = text.find(GRID_OPEN)
    text = text[:h1_end] + intro_html + "\n                    " + text[g:]
    # foto's
    g = text.find(GRID_OPEN) + len(GRID_OPEN)
    mk = text.find(M_PHOTOS_END)
    mk_line = text.rfind("\n", 0, mk) + 1
    text = text[:g] + "\n" + "".join(l + "\n" for l in lines) + text[mk_line:]
    write(page_rel, text)

    # tegel
    t = find_tile(page_rel)
    if t:
        img = t["img"]
        if d.get("tile"):
            img = f"{img_dir}/tegel-{int(time.time())}.jpg"   # nieuwe naam: geen oude versie uit de cache
            save_staged(d["tile"], img)
        sub = d.get("subtitle")
        sub = t["subtitle"] if sub is None else sub.strip()
        parent = read(t["parent"])
        write(t["parent"], parent.replace(t["match"], tile(t["style"], img, page_rel, title, sub), 1))
    # menu
    for name in os.listdir(REPO):
        if name.endswith(".html"):
            tx = read(name)
            new = re.sub(r'<li><a href="' + re.escape(page_rel) + r'">[^<]*</a></li>',
                         lambda m: f'<li><a href="{esc(page_rel)}">{esc(title)}</a></li>', tx)
            if new != tx:
                write(name, new)
    return {"ok": True, "page": page_rel, "count": len(lines)}


def action_album_delete(d):
    page_rel, text = album_page_rel(d.get("page"))
    t = find_tile(page_rel)
    if t:
        parent = read(t["parent"])
        write(t["parent"], re.sub(r"\n[ \t]*" + re.escape(t["match"]), "", parent, count=1))
    for name in os.listdir(REPO):
        if name.endswith(".html") and name != page_rel:
            tx = read(name)
            new = re.sub(r'\n[ \t]*<li><a href="' + re.escape(page_rel) + r'">[^<]*</a></li>', "", tx)
            if new != tx:
                write(name, new)
    os.remove(os.path.join(REPO, page_rel))
    # fotomap enkel weggooien als ALLES erin door de tool gemaakt is (nooit je originele mappen)
    stem = slugify(page_rel[:-5])
    folder = os.path.join(REPO, "images", stem)
    own = re.compile(r"^(" + re.escape(stem) + r"-\d+|tegel(-\d+)?)\.jpg$")
    removed_imgs = False
    if os.path.isdir(folder):
        ok = True
        for root, dirs, files in os.walk(folder):
            rel = os.path.relpath(root, folder)
            if rel not in (".", "thumbs") or any(not own.match(f) and f != ".DS_Store" for f in files):
                ok = False
        if ok:
            shutil.rmtree(folder)
            removed_imgs = True
    return {"ok": True, "page": page_rel, "images": removed_imgs}


# ---------- volgorde van de tegels ----------
TILE_PAGES = {"fotografie": "Fotografie.html", "home": "index.html"}
ARTICLE_RE = re.compile(r"^[ \t]*<article .*</article>[ \t]*$")


def tile_block(page_rel):
    text = read(page_rel)
    a = text.find(M_TILES_BEGIN)
    b = text.find(M_TILES_END)
    if a < 0 or b < 0:
        raise ValueError("Markeringen voor de tegels niet gevonden in " + page_rel)
    a = text.find("\n", a) + 1
    b = text.rfind("\n", 0, b) + 1
    return text, a, b


def action_tiles_get(which):
    page_rel = TILE_PAGES.get(which)
    if not page_rel:
        raise ValueError("Onbekende pagina.")
    text, a, b = tile_block(page_rel)
    tiles = []
    for line in text[a:b].splitlines():
        if ARTICLE_RE.match(line):
            img = re.search(r'<img src="([^"]*)"', line)
            href = re.search(r'<a href="([^"]*)"', line)
            title = re.search(r"<h2>(.*?)</h2>", line)
            tiles.append({"img": html.unescape(img.group(1)) if img else "",
                          "href": html.unescape(href.group(1)) if href else "",
                          "title": html.unescape(title.group(1)) if title else "?"})
    return {"page": page_rel, "tiles": tiles}


def action_tiles_save(d):
    page_rel = TILE_PAGES.get(d.get("which"))
    if not page_rel:
        raise ValueError("Onbekende pagina.")
    text, a, b = tile_block(page_rel)
    lines = [l for l in text[a:b].splitlines() if l.strip()]
    if not all(ARTICLE_RE.match(l) for l in lines):
        raise ValueError("Er staat iets anders dan tegels tussen de markeringen; pas dit met de hand aan.")
    order = d.get("order") or []
    if sorted(order) != list(range(len(lines))):
        raise ValueError("De pagina is intussen gewijzigd. Herlaad en probeer opnieuw.")
    write(page_rel, text[:a] + "".join(lines[i] + "\n" for i in order) + text[b:])
    return {"ok": True, "page": page_rel}


def git(*args):
    r = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def action_state():
    code, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    is_repo = code == 0
    changes = []
    remote = ""
    if is_repo:
        _, st = git("status", "--porcelain", "--untracked-files=all")
        changes = [l for l in st.splitlines() if l.strip()]
        _, remote = git("remote", "get-url", "origin")
    needed = ["assets/css/main.css", "assets/css/fred.css", "assets/js/main.js", "assets/js/jquery.min.js", "images/logo.png"]
    missing = [n for n in needed if not os.path.exists(os.path.join(REPO, n))]
    return {
        "version": VERSION,
        "repo": REPO,
        "missing": missing,
        "is_repo": is_repo,
        "branch": branch if is_repo else "",
        "remote": remote,
        "changes": changes,
        "albums": list_albums(),
        "ratios": {"fotografie": tile_ratio("Fotografie.html"), "home": tile_ratio("index.html")},
        "settings": {"fullPx": FULL_PX, "fullQ": FULL_Q, "thumbPx": THUMB_PX, "thumbQ": THUMB_Q,
                     "tileW": TILE_W, "gridRatio": GRID_RATIO},
    }


def action_publish(data):
    msg = (data.get("message") or "").strip() or "Site bijgewerkt"
    log = []

    def step(*args):
        code, out = git(*args)
        log.append("$ git " + " ".join(args) + ("\n" + out if out else ""))
        return code

    if step("add", "-A") != 0:
        return {"ok": False, "log": "\n\n".join(log)}
    code, st = git("status", "--porcelain")
    if st.strip():
        if step("commit", "-m", msg) != 0:
            return {"ok": False, "log": "\n\n".join(log)}
    else:
        log.append("Geen nieuwe wijzigingen om te committen.")
    if step("pull", "--rebase", "--autostash") != 0:
        log.append("Ophalen van GitHub mislukte. Los dit op (bv. in GitHub Desktop) en probeer opnieuw.")
        return {"ok": False, "log": "\n\n".join(log)}
    ok = step("push") == 0
    if ok:
        log.append("Klaar. GitHub Pages zet de site binnen een minuutje online.")
    else:
        log.append("Pushen mislukte. Gebruik je GitHub Desktop? Open het dan en klik op 'Push origin'.")
    return {"ok": ok, "log": "\n\n".join(log)}


# --------------------------------------------------------------------------
# Webserver
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            with open(os.path.join(TOOL_DIR, "ui.html"), encoding="utf-8") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if url.path == "/api/state":
            return self.send(200, action_state())
        if url.path == "/api/tiles":
            try:
                return self.send(200, action_tiles_get(parse_qs(url.query).get("which", [""])[0]))
            except Exception as e:  # noqa
                return self.send(400, {"error": str(e)})
        if url.path == "/api/album":
            try:
                return self.send(200, action_album_get(parse_qs(url.query).get("page", [""])[0]))
            except Exception as e:  # noqa
                return self.send(400, {"error": str(e)})
        if url.path.startswith("/site/"):
            rel = unquote(url.path[len("/site/"):]) or "index.html"
            full = os.path.realpath(os.path.join(REPO, rel))
            if not full.startswith(os.path.realpath(REPO)) or not os.path.isfile(full):
                return self.send(404, "Niet gevonden", "text/plain")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                return self.send(200, f.read(), ctype)
        if url.path.startswith("/staged/"):
            try:
                with open(staged_path(url.path[len("/staged/"):]), "rb") as f:
                    return self.send(200, f.read(), "image/jpeg")
            except Exception:
                return self.send(404, "", "text/plain")
        self.send(404, "Niet gevonden", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if url.path == "/api/quit":
            self.send(200, {"ok": True})
            threading.Thread(target=SERVER.shutdown, daemon=True).start()
            return
        try:
            if url.path in ("/api/upload", "/api/convert"):
                name = parse_qs(url.query).get("name", ["foto"])[0]
                sid = uuid.uuid4().hex
                remaining = length
                with open(os.path.join(STAGING, sid), "wb") as f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                STAGED_NAMES[sid] = name
                if url.path == "/api/convert":
                    # bv. HEIC dat Chrome niet kan openen: omzetten naar JPEG (draai-info blijft behouden)
                    out = os.path.join(STAGING, sid + ".jpg")
                    make_jpeg(os.path.join(STAGING, sid), out, 100000, 92)
                    with open(out, "rb") as f:
                        return self.send(200, f.read(), "image/jpeg")
                return self.send(200, {"id": sid})
            data = json.loads(self.rfile.read(length) or b"{}")
            with LOCK:
                if url.path == "/api/create":
                    return self.send(200, action_create(data))
                if url.path == "/api/add":
                    return self.send(200, action_add(data))
                if url.path == "/api/album-save":
                    return self.send(200, action_album_save(data))
                if url.path == "/api/tiles-save":
                    return self.send(200, action_tiles_save(data))
                if url.path == "/api/album-delete":
                    return self.send(200, action_album_delete(data))
                if url.path == "/api/publish":
                    return self.send(200, action_publish(data))
            self.send(404, {"error": "onbekend"})
        except Exception as e:  # noqa
            self.send(400, {"error": str(e)})


LOCK = threading.Lock()


SERVER = None


def stop_old_instance():
    """Draait er nog een (oudere) tool? Vraag die te stoppen."""
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/api/quit", data=b"{}"), timeout=2)
    except Exception:
        pass


def main():
    global SERVER
    server = None
    for attempt in range(10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
            break
        except OSError:
            if attempt == 0:
                print("Er draait nog een andere versie van de tool, die wordt gestopt...")
                stop_old_instance()
            time.sleep(0.5)
    if server is None:
        print(f"Poort {PORT} is bezet door een oude versie van de tool.")
        print("Sluit het andere Terminal-venster van de tool en start opnieuw.")
        input("Druk op Enter om te sluiten.")
        return
    SERVER = server
    url = f"http://127.0.0.1:{PORT}/"
    print("Fred Raket site tool")
    print(f"  website-map : {REPO}")
    print(f"  open        : {url}")
    print("Sluit dit venster (of Ctrl+C) om te stoppen.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(STAGING, ignore_errors=True)


if __name__ == "__main__":
    main()
