"""Shared building blocks for the Le Ski static site: routing, images, layout, components."""
import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = ROOT / "src" / "data"

PHONE = "01484 548996"
PHONE_INTL = "+441484548996"
EMAIL = "hello@leski.com"

esc = html.escape

# --------------------------------------------------------------------------
# Routing — every page lives at <path>/index.html; links are made relative
# so the site works from any host, a sub-folder, or straight off disk.
# --------------------------------------------------------------------------
_current = {"path": ""}


def set_current(path):
    _current["path"] = path.strip("/")


def href(path):
    """Relative link from the current page to `path` ('' = home). Keeps #fragments and ?queries."""
    frag = ""
    for sep in ("#", "?"):
        if sep in path:
            path, rest = path.split(sep, 1)
            frag = sep + rest + frag
            break
    target = path.strip("/")
    depth = len(_current["path"].split("/")) if _current["path"] else 0
    up = "../" * depth
    if target.startswith("assets/"):
        return up + target + frag
    return up + (target + "/" if target else "") + "index.html" + frag


def asset(path):
    return href("assets/" + path)


# --------------------------------------------------------------------------
# Images — the source site serves multi-megabyte originals. We record every
# image a page uses and fetch_images.py turns them into responsive WebP.
# --------------------------------------------------------------------------
IMAGE_MANIFEST = {}
SIZES = (800, 1600)
SRC_BASE = "https://www.leski.com/images/photos/large/"


def _img_key(src):
    name = src.rsplit("/", 1)[-1]
    stem = re.sub(r"[^A-Za-z0-9]+", "-", name.rsplit(".", 1)[0]).strip("-").lower()
    return stem[:80]


def img_url(src, w=1600):
    if not src.startswith("http"):
        src = SRC_BASE + src
    key = _img_key(src)
    IMAGE_MANIFEST[key] = src
    return asset(f"img/{key}-{w}.webp")


def img(src, alt="", cls="", sizes="100vw", eager=False, w=None):
    """<img> with srcset at 800/1600."""
    s800, s1600 = img_url(src, 800), img_url(src, 1600)
    attrs = f'src="{s800 if w == 800 else s1600}" srcset="{s800} 800w, {s1600} 1600w" sizes="{sizes}" alt="{esc(alt)}"'
    attrs += ' loading="eager" fetchpriority="high"' if eager else ' loading="lazy" decoding="async"'
    if cls:
        attrs += f' class="{cls}"'
    return f"<img {attrs}>"


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
CHALETS = json.loads((DATA / "chalets.json").read_text())

RESORTS = {
    "courchevel": dict(name="Courchevel", path="courchevel", altitude="1650m", area="Les 3 Vallées · 600km",
                       blurb="Our home since 1982 — the world's largest ski area on the doorstep.",
                       hero="IMG_1353.jpg", transfer="90 min"),
    "val-d-isere": dict(name="Val d'Isère", path="val-disere", altitude="1850m", area="Espace Killy · 300km",
                        blurb="High, snowsure and properly Alpine, with a village that buzzes after dark.",
                        hero="DSF1562.jpg", transfer="2 hrs"),
    "la-tania": dict(name="Courchevel La Tania", short="La Tania", path="la-tania", altitude="1400m", area="Les 3 Vallées · 600km",
                     blurb="A car-free village in the trees — ideal for families and first-timers.",
                     hero="La-tania-drone-shot.png", transfer="80 min"),
    "tignes": dict(name="Tignes", path="tignes", altitude="2100m", area="Espace Killy · 300km",
                   blurb="Glacier-high and reliably snowy from the first week to the last.",
                   hero="AP89007-editcandyparant.com.jpg", transfer="2 hrs"),
}
for key, r in RESORTS.items():
    r["key"] = key
    r.setdefault("short", r["name"])
    r["chalets"] = sorted([c for c in CHALETS if c["resort"] == key], key=lambda c: (int(re.split(r"\D", c["sleeps"])[0] or 0), c["name"]))
    prices = [c["from_price"] for c in r["chalets"] if c["from_price"]]
    r["from"] = min(prices) if prices else None


def chalet_path(c):
    return f"{c['resort']}/chalets/{c['slug']}"


def chalet_short(c):
    return re.sub(r"^Chalet\s+", "", c["name"])


def chalet_by_slug(slug):
    return next(c for c in CHALETS if c["slug"] == slug)


def money(n):
    return f"£{n:,}"


# --------------------------------------------------------------------------
# Icons (inline, stroke-based, 24px grid)
# --------------------------------------------------------------------------
ICONS = {
    "plane": '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
    "bus": '<path d="M8 6v6M15 6v6M2 12h19.6M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"/><circle cx="7" cy="18" r="2"/><path d="M9 18h5"/><circle cx="16" cy="18" r="2"/>',
    "chef": '<path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><path d="M6 17h12"/>',
    "wine": '<path d="M8 22h8M7 10h10M12 15v7M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z"/>',
    "glass": '<path d="M8 22h8M12 11v11M5 2l1 6a6 6 0 0 0 12 0l1-6Z"/>',
    "cup": '<path d="M17 8h1a4 4 0 1 1 0 8h-1"/><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/><path d="M6 2v2M10 2v2M14 2v2"/>',
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "bed": '<path d="M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9"/>',
    "star": '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
    "award": '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    "heart": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "mountain": '<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>',
    "snow": '<path d="M2 12h20M12 2v20m-8-4 16-12M4 6l16 12"/>',
    "wifi": '<path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"/>',
    "spa": '<path d="M12 22c4.97 0 9-2.69 9-6s-4.03-6-9-6-9 2.69-9 6 4.03 6 9 6Z"/><path d="M8 4c0 1.5 1 2 1 3.5S8 10 8 10M12 2c0 1.5 1 2 1 3.5S12 8 12 8M16 4c0 1.5 1 2 1 3.5S16 10 16 10"/>',
    "fire": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "map": '<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4z"/><path d="M8 2v16M16 6v16"/>',
    "child": '<circle cx="12" cy="5" r="3"/><path d="M9 21v-4l-3-3 3-5h6l3 5-3 3v4"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "arrow": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "chev": '<path d="m6 9 6 6 6-6"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
    "ski": '<path d="m3 21 18-6M10 13l-1.5 4.5M14 11.5 12 18"/><circle cx="15" cy="4" r="2"/><path d="m8 9 4-2 3 3 3 1"/>',
    "tv": '<rect x="2" y="7" width="20" height="15" rx="2"/><path d="m17 2-5 5-5-5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
}


def icon(name, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


# --------------------------------------------------------------------------
# Navigation model
# --------------------------------------------------------------------------
HOLIDAYS = [
    ("chalet-holidays/christmas", "Christmas", "Sun 20 Dec 2026"),
    ("chalet-holidays/newyears", "New Year", "Sun 27 Dec 2026"),
    ("chalet-holidays/february-half-term", "February half term", "Sun 14 Feb 2027"),
    ("chalet-holidays/easter", "Easter", "Sun 28 Mar 2027"),
]

NAV = [
    ("Chalets", "chalets", None),  # mega built dynamically
    ("Resorts", "resorts", [
        ("Our resorts", [(RESORTS[k]["path"], RESORTS[k]["name"]) for k in RESORTS]),
        ("Resort guides", [
            ("chalet-holidays/holiday-guide", "Holiday guide"),
            ("chalet-holidays/restaurants", "Restaurant guide"),
            ("chalet-holidays/bars", "Bars & après-ski"),
            ("chalet-holidays/activities", "Non-ski activities"),
            ("aquamotion", "Aquamotion spa & pools"),
        ]),
        ("Plan your skiing", [
            ("chalet-holidays/passes", "Lift passes"),
            ("chalet-holidays/lessons", "Ski schools"),
            ("chalet-holidays/shops", "Ski hire"),
            ("chalet-holidays/piste-maps", "Piste maps"),
            ("chalet-holidays/resort-maps", "Village maps"),
            ("chalet-holidays/weather", "Weather & webcams"),
        ]),
    ]),
    ("Holidays", "holidays", [
        ("School holidays", [(p, n) for p, n, _ in HOLIDAYS]),
        ("Who's coming?", [
            ("chalet-holidays/family", "Family ski holidays"),
            ("chalet-holidays/family/ski-school-children", "Ski school for children"),
            ("chalet-holidays/skiing-for-beginners", "Skiing for beginners"),
            ("chalet-holidays/clinics", "Ski clinics"),
            ("chalet-holidays/discounts", "Offers & discounts"),
        ]),
    ]),
    ("The Le Ski way", "service", [
        ("Your holiday", [
            ("chalet-holidays/included", "What's included"),
            ("chalet-holidays/flights", "Flights & transfers"),
            ("chalet-holidays/staff", "Our chalet teams"),
            ("feefo-reviews", "Guest reviews"),
        ]),
        ("Food & wine", [
            ("chalet-holidays/food", "Chalet food"),
            ("chalet-holidays/wine", "Our wines"),
            ("chalet-holidays/special-diets", "Special diets"),
        ]),
    ]),
    ("About", "about", [
        ("Le Ski", [
            ("chalet-holidays", "Who we are"),
            ("chalet-holidays/40-years-anniversary", "40 years of Le Ski"),
            ("chalet-holidays/press", "In the press"),
            ("chalet-holidays/bonding", "Is my money safe?"),
            ("chalet-holidays/green-policies", "Green policy"),
            ("chalet-holidays/Snow-Camp-Fund", "Le Ski & charity"),
        ]),
        ("Help", [
            ("chalet-holidays/faqs", "FAQs"),
            ("chalet-holidays/contact", "Contact us"),
            ("blog", "Blog"),
            ("ski-jobs/staff-experiences", "Work for us"),
        ]),
    ]),
]


def _mega_chalets():
    def group(key):
        r = RESORTS[key]
        lis = "".join(
            f'<li><a href="{href(chalet_path(c))}"><span>{esc(chalet_short(c))}'
            + ('<span class="tag-new">NEW</span>' if c.get("new") else "")
            + f'</span><small>sleeps {esc(c["sleeps"])}</small></a></li>'
            for c in r["chalets"])
        return f'<h6><a href="{href(r["path"])}">{esc(r["short"])}</a></h6><ul>{lis}</ul>'

    feature = (f'<div class="mega-feature"><div><strong>Not sure which chalet?</strong>'
               f'<p>Filter all {len(CHALETS)} chalets by date, group size, resort and facilities — or call us and we\'ll shortlist a few.</p></div>'
               f'<a class="btn btn--mint btn--sm" href="{href("chalet-holidays/chalet-finder")}">Open chalet finder</a></div>')
    # Tignes has a single chalet, so it shares a column with La Tania
    return ('<div class="mega mega--wide"><div class="mega-grid" style="--cols:4">'
            f'<div>{group("courchevel")}</div><div>{group("val-d-isere")}</div>'
            f'<div>{group("la-tania")}<div style="margin-top:24px">{group("tignes")}</div></div>'
            f'{feature}</div></div>')


def _mega(groups):
    cols = "".join(
        f'<div><h6>{esc(title)}</h6><ul>' + "".join(f'<li><a href="{href(p)}">{esc(n)}</a></li>' for p, n in links) + "</ul></div>"
        for title, links in groups)
    return f'<div class="mega" style="--cols:{len(groups)}"><div class="mega-grid">{cols}</div></div>'


def header(active=""):
    items = []
    for label, key, groups in NAV:
        panel = _mega_chalets() if key == "chalets" else _mega(groups)
        cur = ' aria-current="page"' if key == active else ""
        items.append(f'<li class="nav-item" data-mega><button class="nav-link" type="button" aria-expanded="false"{cur}>{label}{icon("chev")}</button>{panel}</li>')

    drawer_groups = []
    chalet_links = [(href("chalet-holidays/chalet-finder"), "Chalet finder — all chalets")] + [
        (href(RESORTS[k]["path"]), f'{RESORTS[k]["name"]} chalets') for k in RESORTS]
    drawer_groups.append(("Chalets", chalet_links))
    for label, key, groups in NAV[1:]:
        drawer_groups.append((label, [(href(p), n) for _, links in groups for p, n in links]))
    drawer = "".join(
        f'<details><summary>{esc(t)}</summary><ul>' + "".join(f'<li><a href="{h}">{esc(n)}</a></li>' for h, n in links) + "</ul></details>"
        for t, links in drawer_groups)

    return f'''
<a class="visually-hidden" href="#main">Skip to content</a>
<div class="utility"><div class="wrap">
  <div class="utility-trust">
    <span>{icon("shield")} ATOL &amp; ABTOT protected</span>
    <span>{icon("heart")} Family owned since 1982</span>
    <span>{icon("award")} Nominated: Best Ski Operator 2026</span>
  </div>
  <div class="utility-links">
    <a href="{href("feefo-reviews")}">Reviews</a>
    <a href="{href("chalet-holidays/faqs")}">FAQs</a>
    <a href="{href("chalet-holidays/contact")}">Contact</a>
  </div>
</div></div>
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="{href("")}" aria-label="Le Ski home"><img src="{asset("logo.svg")}" alt="Le Ski" width="68" height="40"><span>The chalet<br>specialists</span></a>
    <nav class="nav" aria-label="Main"><ul>{"".join(items)}</ul></nav>
    <div class="header-cta">
      <a class="header-phone" href="tel:{PHONE_INTL}"><small>Talk to our UK team</small><strong>{PHONE}</strong></a>
      <a class="btn" href="{href("chalet-holidays/enquiry")}">Enquire</a>
      <button class="menu-toggle" type="button" data-drawer-open aria-label="Open menu">{icon("menu")}</button>
    </div>
  </div>
</header>
<div class="drawer" role="dialog" aria-modal="true" aria-label="Menu">
  <div class="drawer-scrim" data-drawer-close></div>
  <div class="drawer-panel">
    <div class="drawer-top"><img src="{asset("logo.svg")}" alt="Le Ski" height="34" style="height:34px;width:auto"><button class="menu-toggle" style="display:inline-flex" type="button" data-drawer-close aria-label="Close menu">{icon("close")}</button></div>
    {drawer}
    <a class="btn" href="{href("chalet-holidays/enquiry")}">Make an enquiry</a>
    <a class="btn btn--ghost" href="tel:{PHONE_INTL}">{icon("phone")} {PHONE}</a>
  </div>
</div>'''


def footer():
    cols = [
        ("Chalets", [(RESORTS[k]["path"], RESORTS[k]["name"]) for k in RESORTS] + [("chalet-holidays/chalet-finder", "Chalet finder")]),
        ("Your holiday", [("chalet-holidays/included", "What's included"), ("chalet-holidays/flights", "Flights & transfers"),
                          ("chalet-holidays/food", "Food & wine"), ("chalet-holidays/family", "Family holidays"),
                          ("chalet-holidays/discounts", "Offers & discounts")]),
        ("About", [("chalet-holidays", "Who we are"), ("feefo-reviews", "Guest reviews"), ("chalet-holidays/press", "In the press"),
                   ("ski-jobs/staff-experiences", "Work for us"), ("blog", "Blog")]),
        ("Help", [("chalet-holidays/contact", "Contact us"), ("chalet-holidays/faqs", "FAQs"), ("chalet-holidays/bonding", "Is my money safe?"),
                  ("chalet-holidays/insurance", "Insurance"), ("chalet-holidays/links", "Useful links")]),
    ]
    colhtml = "".join(f'<div><h6>{t}</h6><ul>' + "".join(f'<li><a href="{href(p)}">{esc(n)}</a></li>' for p, n in links) + "</ul></div>" for t, links in cols)
    return f'''
<footer class="site-footer">
  <div class="wrap">
    <div class="footer-top">
      <div class="footer-brand">
        <img src="{asset("logo-white.svg")}" alt="Le Ski" width="75" height="44">
        <p>Family-owned catered chalet holidays in Courchevel, Val d'Isère, La Tania and Tignes — with our own flights and transfers — since 1982.</p>
        <p><a href="tel:{PHONE_INTL}">{PHONE}</a><br><a href="mailto:{EMAIL}">{EMAIL}</a></p>
        <form class="newsletter" onsubmit="event.preventDefault();this.querySelector('button').textContent='Thank you'">
          <label class="visually-hidden" for="nl">Email address</label>
          <input id="nl" type="email" placeholder="Snow news &amp; early offers" required>
          <button class="btn btn--mint btn--sm" type="submit">Sign up</button>
        </form>
      </div>
      {colhtml}
    </div>
    <div class="footer-accred">
      <span class="accred"><b>ATOL</b>ATOL protected</span>
      <span class="accred"><b>ABTOT</b>ABTOT member</span>
      <span class="accred"><b>100%</b>Financial protection</span>
      <span class="accred"><b>QC</b>Quality Chalet</span>
      <span class="accred"><b>2026</b>Nominated: Best Ski Operator</span>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Le Ski Ltd · Stirling House, 139 Netheroyd Hill Road, Huddersfield HD2 2LX</span>
      <ul>
        <li><a href="{href("chalet-holidays/booking-conditions")}">Booking conditions</a></li>
        <li><a href="{href("chalet-holidays/privacy-policy")}">Privacy</a></li>
        <li><a href="{href("gdpr-regulations")}">GDPR</a></li>
        <li><a href="{href("chalet-holidays/green-policies")}">Green policy</a></li>
      </ul>
    </div>
  </div>
</footer>'''


def layout(path, title, description, body, active="", og_image=None):
    full_title = title if "Le Ski" in title else f"{title} | Le Ski"
    og = f'<meta property="og:image" content="{og_image}">' if og_image else ""
    return f'''<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(description)}">
{og}
<meta name="theme-color" content="#0B2C3B">
<link rel="icon" href="{asset("logo.svg")}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..600;1,9..144,300..500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{asset("site.css")}">
</head>
<body>
{header(active)}
<main id="main">
{body}
</main>
{footer()}
<script src="{asset("site.js")}" defer></script>
</body>
</html>
'''


def write_page(path, html_text):
    out = SITE / path / "index.html" if path else SITE / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text)
    return out


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
def crumbs(trail):
    items = "".join(
        f'<li><a href="{href(p)}">{esc(n)}</a></li>' if p is not None else f'<li aria-current="page">{esc(n)}</li>'
        for p, n in trail)
    return f'<ol class="crumbs">{items}</ol>'


def hero(image, title_html, lead="", eyebrow="", extra="", cls="", trail=None, alt=""):
    return f'''
<section class="hero {cls}">
  <div class="hero-media">{img(image, alt, sizes="100vw", eager=True)}</div>
  <div class="wrap">
    {crumbs(trail) if trail else ""}
    {f'<span class="eyebrow">{eyebrow}</span>' if eyebrow else ""}
    <h1>{title_html}</h1>
    {f'<p class="lead">{lead}</p>' if lead else ""}
    {extra}
  </div>
</section>'''


def search_panel(resort=""):
    dates = ["29 Nov 2026", "6 Dec 2026", "13 Dec 2026", "20 Dec 2026", "27 Dec 2026", "3 Jan 2027", "10 Jan 2027", "17 Jan 2027",
             "24 Jan 2027", "31 Jan 2027", "7 Feb 2027", "14 Feb 2027", "21 Feb 2027", "28 Feb 2027", "7 Mar 2027", "14 Mar 2027",
             "21 Mar 2027", "28 Mar 2027", "4 Apr 2027", "11 Apr 2027"]
    opts_d = "".join(f'<option value="{d}">Sun {d}</option>' for d in dates)
    opts_g = "".join(f'<option value="{g}">{g} guests</option>' for g in ["2-6", "7-10", "11-14", "15-18", "19-25"])
    opts_r = "".join(f'<option value="{k}"{" selected" if k == resort else ""}>{esc(r["name"])}</option>' for k, r in RESORTS.items())
    return f'''
<form class="search" data-search action="{href("chalet-holidays/chalet-finder")}">
  <label><span>When</span><select name="date"><option value="">Any Sunday departure</option>{opts_d}</select></label>
  <label><span>Who</span><select name="guests"><option value="">Any group size</option>{opts_g}</select></label>
  <label><span>Where</span><select name="resort"><option value="">All four resorts</option>{opts_r}</select></label>
  <button class="btn" type="submit">Find a chalet {icon("arrow")}</button>
</form>'''


def trustbar():
    return f'''
<section class="trustbar"><div class="wrap"><ul>
  <li>{icon("heart")}<span><strong>Family owned</strong>43rd season in the Alps</span></li>
  <li>{icon("shield")}<span><strong>100% protected</strong>ATOL &amp; ABTOT bonded</span></li>
  <li>{icon("plane")}<span><strong>Our own flights</strong>Gatwick &amp; Manchester</span></li>
  <li>{icon("award")}<span><strong>Best Ski Operator</strong>Nominated 2026</span></li>
  <li>{icon("users")}<span><strong>5,000 guests</strong>looked after each winter</span></li>
</ul></div></section>'''


def chalet_features_chips(c, n=3):
    out = []
    feats = " ".join(c["features"] + c["highlights"]).lower()
    if "hot tub" in feats:
        out.append(("spa", "Hot tub"))
    if "sauna" in feats:
        out.append(("spa", "Sauna"))
    if "steam" in feats:
        out.append(("spa", "Steam room"))
    if "fire" in feats:
        out.append(("fire", "Log fire"))
    if "piste" in feats or "ski-in" in feats:
        out.append(("ski", "Near the piste"))
    if "view" in feats:
        out.append(("mountain", "Views"))
    return "".join(f'<span class="chip">{icon(i)}{t}</span>' for i, t in out[:n])


def chalet_card(c, sizes="(max-width: 720px) 100vw, (max-width: 980px) 50vw, 33vw"):
    r = RESORTS[c["resort"]]
    cover = c["gallery"][0]["src"] if c["gallery"] else ""
    badges = ""
    if c.get("new"):
        badges += '<span class="badge badge--mint">New for 26/27</span>'
    if c["offers"]:
        badges += '<span class="badge badge--offer">Free places offer</span>'
    price = (f'<div class="price"><small>From, per person</small><strong>{money(c["from_price"])}</strong> <span>incl. flights</span></div>'
             if c["from_price"] else '<div class="price"><small>Prices</small><strong>On request</strong></div>')
    data = f'data-resort="{c["resort"]}" data-sleeps="{esc(c["sleeps"])}" data-price="{c["from_price"] or 0}"'
    return f'''
<article class="card" {data}>
  <div class="card-media">{badges}{img(cover, c["gallery"][0]["alt"] if c["gallery"] else c["name"], sizes=sizes, w=800)}</div>
  <div class="card-body">
    <div class="card-meta"><span>{esc(r["name"])}</span><span class="dot"></span><span>Sleeps {esc(c["sleeps"])}</span></div>
    <h3><a href="{href(chalet_path(c))}">{esc(c["name"])}</a></h3>
    <p>{esc(c["summary"])}</p>
    <div class="chips">{chalet_features_chips(c)}</div>
    <div class="card-foot">{price}<span class="link-arrow">View</span></div>
  </div>
</article>'''


def cta_band(title="Talk to someone who's been there", text=None):
    text = text or ("Our UK team have worked at Le Ski for a combined 184 years. Tell us who's coming and when, "
                    "and we'll suggest the chalets that suit you best — no hard sell, ever.")
    return f'''
<section class="section-tight"><div class="wrap">
  <div class="cta-band reveal">
    <div>
      <span class="eyebrow">Let's plan your week</span>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
    <div class="contact-lines">
      <a class="contact-line" href="tel:{PHONE_INTL}">{icon("phone")}<span><small>Call us · Mon–Fri 9–5.30, Sat 9–1</small><strong>{PHONE}</strong></span></a>
      <a class="contact-line" href="mailto:{EMAIL}">{icon("mail")}<span><small>Email the team</small><strong>{EMAIL}</strong></span></a>
      <a class="contact-line" href="{href("chalet-holidays/enquiry")}">{icon("calendar")}<span><small>Prefer to write it down?</small><strong>Send an enquiry</strong></span></a>
    </div>
  </div>
</div></section>'''


REVIEWS = [
    ("Amazing from start to finish", "Fantastic service from start to finish. The team were amazing and made us feel like celebrities. Lucy was in touch before we even left the UK to ensure we had any restaurant bookings we wanted.", "Verified Feefo review"),
    ("Courchevel 2026", "Having been on multiple Le Ski holidays, I cannot remember any of our fellow guests who have not committed to another Le Ski experience or are repeat customers. It speaks for itself!", "Timothy D. · Feefo"),
    ("Fantastic ski holiday in Val d'Isère", "The staff in the UK office are knowledgeable, very helpful and very friendly. With flights and transfers included it is really easy to organise and great value. Our chalet was beautiful.", "Rachel M. · Feefo"),
    ("Perfect Courchevel", "The transport arrangements were seamless and comfortable. The staff were great, the food was excellent and the wine plentiful. Our fellow guests all said they would travel with Le Ski again.", "Verified Feefo review"),
    ("Wonderful holiday", "The flights and transfers worked very well. The beds were comfortable and the hot water supply was very good. The food was interesting and very well cooked and presented.", "Verified Feefo review"),
    ("Excellent service", "Excellent chalet and good food. Chalet staff were professional and had a great attention to detail to make our stay really special.", "Verified Feefo review"),
]


def reviews_block(n=3, head=True):
    cards = "".join(
        f'<article class="review"><span class="stars" aria-label="5 out of 5">★★★★★</span><h3>{esc(t)}</h3><p>“{esc(b)}”</p><footer>{esc(a)}</footer></article>'
        for t, b, a in REVIEWS[:n])
    top = ""
    if head:
        top = f'''<div class="section-head"><div><span class="eyebrow">Guest reviews</span><h2>Many happy re-runs</h2></div>
<p>Most of our guests have skied with us before. Read hundreds of independent, verified reviews on Feefo. <a class="link-arrow" href="{href("feefo-reviews")}">All reviews</a></p></div>'''
    return f'{top}<div class="reviews">{cards}</div>'
