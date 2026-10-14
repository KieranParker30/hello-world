"""Resort overviews, chalet detail pages and the chalet finder."""
import datetime as dt
import json
import re

from lib import *
from data.resorts import RESORT_COPY

GALLERY_MAX = 10
MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr"]


def iso(d):
    """'13-Dec-2026' -> '2026-12-13'"""
    return dt.datetime.strptime(d, "%d-%b-%Y").date().isoformat()


def nice_date(d, fmt="%a %-d %b %Y"):
    return dt.datetime.strptime(d, "%d-%b-%Y").strftime(fmt)


def parse_price(p):
    """-> (status, amount, partial)  status in available|sold|call"""
    if p.strip().lower() == "sold":
        return "sold", None, False
    m = re.search(r"\d+", p)
    n = int(m.group()) if m else 0
    if not n:
        return "call", None, False
    return "available", n, "†" in p


def sleeps_range(c):
    nums = [int(x) for x in re.findall(r"\d+", c["sleeps"])]
    return (min(nums), max(nums)) if nums else (0, 0)


def facility_flags(c):
    text = " ".join(c["features"] + c["highlights"] + c["paras"]).lower()
    return {
        "hottub": "hot tub" in text,
        "sauna": "sauna" in text or "steam" in text,
        "fire": "fire" in text or "stove" in text,
        "piste": any(k in text for k in ("piste-side", "piste side", "ski in", "ski-in", "seconds from the slopes", "2 mins from the slopes")),
        "offer": bool(c["offers"]),
    }


# ---------------------------------------------------------------------------
# Resort overview
# ---------------------------------------------------------------------------
def build_resort(key):
    r, copy = RESORTS[key], RESORT_COPY[key]
    set_current(r["path"])
    stats = "".join(f'<div class="stat"><strong>{v}</strong><span>{esc(l)}</span></div>' for v, l in copy["stats"])
    skiing = "".join(
        f'<div class="pillar"><span class="num">0{i + 1}</span><h3>{t}</h3><p>{esc(d)}</p></div>'
        for i, (t, d) in enumerate(copy["skiing"]))
    lo, hi = min(sleeps_range(c)[0] for c in r["chalets"]), max(sleeps_range(c)[1] for c in r["chalets"])
    others = "".join(
        f'<a class="date-card" href="{href(o["path"])}"><small>{o["altitude"]} · {o["transfer"]} transfer</small><strong>{esc(o["name"])}</strong><span class="link-arrow">{len(o["chalets"])} chalet{"s" if len(o["chalets"]) > 1 else ""}</span></a>'
        for k, o in RESORTS.items() if k != key)
    guides = [("chalet-holidays/holiday-guide", "Holiday guide"), ("chalet-holidays/restaurants", "Restaurants"),
              ("chalet-holidays/bars", "Bars & après"), ("chalet-holidays/passes", "Lift passes"),
              ("chalet-holidays/lessons", "Ski schools"), ("chalet-holidays/piste-maps", "Piste maps")]
    guide_links = "".join(f'<li><a href="{href(p)}">{n}</a></li>' for p, n in guides)

    body = f'''
{hero(r["hero"], copy["h1"], copy["lead"], eyebrow=f'{r["altitude"]} · {r["area"]}', cls="hero--page",
      trail=[("", "Home"), (None, r["name"])], alt=f"{r['name']} ski resort",
      extra=f'<div class="btn-row" style="margin-top:28px"><a class="btn btn--mint" href="#chalets">See {len(r["chalets"])} chalet{"s" if len(r["chalets"]) > 1 else ""}</a><a class="btn btn--light" href="{href("chalet-holidays/enquiry")}">Make an enquiry</a></div>')}

<section class="section-tight section--paper" style="border-bottom:1px solid var(--stone-200)"><div class="wrap"><div class="stats">{stats}</div></div></section>

<section class="section"><div class="wrap">
  <div class="split">
    <div>
      <span class="eyebrow">Why we love it</span>
      <h2>{esc(copy["village"])}</h2>
      {"".join(f"<p>{esc(p)}</p>" for p in copy["intro"])}
    </div>
    <aside class="aside-card" style="align-self:start">
      <h4>Plan your week in {esc(r["short"])}</h4>
      <p>Our Guest Services team in resort can book lift passes, lessons, hire and restaurant tables for you.</p>
      <ul>{guide_links}</ul>
    </aside>
  </div>
</div></section>

<section class="section section--stone" id="chalets"><div class="wrap">
  <div class="section-head">
    <div><span class="eyebrow">Chalets in {esc(r["short"])}</span><h2>{len(r["chalets"])} chalet{"s" if len(r["chalets"]) > 1 else ""}, sleeping {lo} to {hi}</h2></div>
    <p>Every chalet comes with the same food, wine and service. Prices are per person and include flights, transfers and catering. <a class="link-arrow" href="{href("chalet-holidays/chalet-finder?resort=" + key)}">Filter by date</a></p>
  </div>
  <div class="grid grid-3">{"".join(chalet_card(c) for c in sorted(r["chalets"], key=lambda c: c["from_price"] or 99999))}</div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head"><div><span class="eyebrow">The skiing</span><h2>Something for every level</h2></div>
  <p><a class="link-arrow" href="{href("chalet-holidays/piste-maps")}">Piste maps</a></p></div>
  <div class="pillars">{skiing}</div>
</div></section>

<section class="section section--paper"><div class="wrap">
  <div class="split split--rev">
    <div class="split-media split-media--wide reveal">{img(copy["offimg"], f"Off the slopes in {r['name']}", sizes="(max-width: 980px) 100vw, 50vw")}</div>
    <div>
      <span class="eyebrow">Off the slopes</span>
      <h2>Not everyone wants to ski every day</h2>
      <p class="lead">{esc(copy["offslope"])}</p>
      <div class="btn-row" style="margin-top:24px"><a class="btn btn--ghost" href="{href("chalet-holidays/activities")}">Non-ski activities</a><a class="btn btn--ghost" href="{href("chalet-holidays/restaurants")}">Restaurant guide</a></div>
    </div>
  </div>
</div></section>

<section class="section"><div class="wrap">
  <blockquote class="quote">“{esc(copy["quote"][0])}”<cite>{esc(copy["quote"][1])}</cite></blockquote>
</div></section>

<section class="section-tight section--stone"><div class="wrap">
  <div class="section-head"><div><span class="eyebrow">Compare</span><h2>Our other resorts</h2></div></div>
  <div class="dates dates--3">{others}</div>
</div></section>

{cta_band(f"Not sure which {esc(r['short'])} chalet?")}
'''
    title = f"Catered Ski Chalets in {r['name']}"
    write_page(r["path"], layout(r["path"], title,
                                 f"{len(r['chalets'])} catered chalets in {r['name']} with flights, transfers, chalet host and unlimited wine. {copy['lead'][:90]}",
                                 body, active="resorts"))


# ---------------------------------------------------------------------------
# Chalet detail
# ---------------------------------------------------------------------------
def availability(c):
    by_month = {}
    for p in c["prices"]:
        status, amount, partial = parse_price(p["price"])
        m = dt.datetime.strptime(p["date"], "%d-%b-%Y")
        by_month.setdefault(m.strftime("%B %Y"), []).append((p, status, amount, partial))
    blocks = []
    for month, rows in by_month.items():
        cells = []
        for p, status, amount, partial in rows:
            q = f'?chalet={c["slug"]}&date={iso(p["date"])}'
            if status == "available":
                cells.append(
                    f'<a class="avail avail--open" href="{href("chalet-holidays/enquiry" + q)}"><span class="avail-date">{nice_date(p["date"], "%a %-d %b")}</span>'
                    f'<strong>{money(amount)}{"<sup>†</sup>" if partial else ""}</strong><span class="avail-cta">Enquire</span></a>')
            elif status == "call":
                cells.append(f'<a class="avail avail--call" href="tel:{PHONE_INTL}"><span class="avail-date">{nice_date(p["date"], "%a %-d %b")}</span><strong>Call us</strong><span class="avail-cta">{PHONE}</span></a>')
            else:
                cells.append(f'<a class="avail avail--sold" href="{href("chalet-holidays/enquiry" + q + "&waitlist=1")}"><span class="avail-date">{nice_date(p["date"], "%a %-d %b")}</span><strong>Sold</strong><span class="avail-cta">Join waitlist</span></a>')
        blocks.append(f'<div class="avail-month"><h4>{month}</h4><div class="avail-grid">{"".join(cells)}</div></div>')
    return "".join(blocks)


def similar(c, n=3):
    lo, hi = sleeps_range(c)
    pool = [x for x in CHALETS if x is not c]
    pool.sort(key=lambda x: (x["resort"] != c["resort"], abs(sleeps_range(x)[1] - hi)))
    return pool[:n]


def build_chalet(c):
    r = RESORTS[c["resort"]]
    path = chalet_path(c)
    set_current(path)
    gal = c["gallery"][:GALLERY_MAX]
    lo, hi = sleeps_range(c)
    flags = facility_flags(c)

    mosaic = "".join(
        f'<button class="mosaic-item" type="button" data-lightbox-open="{i}" aria-label="Open photo {i + 1}">{img(g["src"], g["alt"], sizes="(max-width: 720px) 100vw, " + ("60vw" if i == 0 else "20vw"), eager=(i == 0), w=(None if i == 0 else 800))}</button>'
        for i, g in enumerate(gal[:5]))
    slides = "".join(f'<figure data-slide><img data-src="{img_url(g["src"], 1600)}" alt="{esc(g["alt"])}"><figcaption>{esc(g["alt"])}</figcaption></figure>' for g in gal)

    available = [(p, parse_price(p["price"])) for p in c["prices"]]
    open_weeks = [(p, a) for p, (s, a, _) in available if s == "available"]
    next_weeks = "".join(
        f'<li><a href="{href("chalet-holidays/enquiry?chalet=" + c["slug"] + "&date=" + iso(p["date"]))}"><span>{nice_date(p["date"], "%a %-d %b")}</span><strong>{money(a)}</strong></a></li>'
        for p, a in open_weeks[:4])
    offers = "".join(f"<p><strong>{esc(o)}</strong></p>" for o in c["offers"])
    paras = [p for p in c["paras"] if "smart tv" not in p.lower() and "don't hesitate to call" not in p.lower()]
    smart_tv = any("smart tv" in p.lower() for p in c["paras"])
    feats = [f.strip() for f in c["features"]] + (["Smart TV"] if smart_tv else [])
    feat_icons = {"cater": "chef", "hot tub": "spa", "sauna": "spa", "steam": "spa", "view": "mountain", "fire": "fire",
                  "lounge": "home", "terrace": "sun", "balcon": "sun", "tv": "tv", "media": "tv", "wifi": "wifi", "piste": "ski", "lift": "ski"}

    def ficon(f):
        lf = f.lower()
        return next((v for k, v in feat_icons.items() if k in lf), "check")

    features = "".join(f'<li>{icon(ficon(f))}<span>{esc(f)}</span></li>' for f in feats)
    highlights = "".join(f"<li>{icon('check')}{esc(h)}</li>" for h in c["highlights"])
    rooms = "".join(f'<li><span class="room-n">{esc(x.split(" ", 1)[0])}</span><span>{esc(x.split(" ", 1)[1] if " " in x else x)}</span></li>' for x in c["rooms"] if x.strip())
    plan = f'<figure class="floorplan">{img(c["plan"], f"Floorplan of {c['name']}", sizes="(max-width: 980px) 100vw, 60vw")}</figure>' if c["plan"] else ""
    sim = "".join(chalet_card(x) for x in similar(c))
    from_html = (f'<div class="price"><small>From, per person, 7 nights</small><strong style="font-size:2rem">{money(c["from_price"])}</strong></div>'
                 if c["from_price"] else '<div class="price"><small>Prices</small><strong>On request</strong></div>')
    badges = ('<span class="chip" style="background:var(--mint-100);color:var(--petrol-700)">New for 2026/27</span>' if c.get("new") else "")

    body = f'''
<section class="chalet-top"><div class="wrap">
  {crumbs([("", "Home"), (r["path"], r["name"]), (None, c["name"])])}
  <div class="chalet-title">
    <div>
      <h1>{esc(c["name"])}</h1>
      <div class="chalet-meta">
        <span>{icon("pin")}{esc(r["name"])}</span>
        <span>{icon("users")}Sleeps {esc(c["sleeps"])}</span>
        <span>{icon("bed")}{len([x for x in c["rooms"] if x.strip()])} bedrooms</span>
        {badges}
      </div>
    </div>
    <div class="btn-row"><a class="btn btn--ghost btn--sm" href="#availability">{icon("calendar")} Availability</a></div>
  </div>
  <div class="mosaic mosaic--{min(len(gal), 5)}">{mosaic}
    <button class="btn btn--sm mosaic-all" type="button" data-lightbox-open="0">View all {len(gal)} photos</button>
  </div>
</div></section>

<section class="section-tight" style="padding-top:clamp(32px,4vw,56px)"><div class="wrap">
  <div class="chalet-layout">
    <div class="chalet-main">
      <p class="lead" style="max-width:none;color:var(--petrol-900);font-family:var(--font-display);font-size:clamp(1.4rem,2.2vw,1.75rem);line-height:1.4">{esc(c["summary"])}.</p>
      {f'<div class="offer-callout">{icon("star")}<div>{offers}<p class="small">Ask us for details when you enquire.</p></div></div>' if offers else ""}
      <div class="prose">{"".join(f"<p>{esc(p)}</p>" for p in paras)}</div>

      <h2 class="h-sub">Highlights</h2>
      <ul class="ticks">{highlights}</ul>

      <h2 class="h-sub">Chalet features</h2>
      <ul class="features">{features}</ul>

      {f'<h2 class="h-sub">Bedrooms</h2><ul class="rooms">{rooms}</ul>' if rooms else ""}
      {plan}

      <h2 class="h-sub" id="availability">Availability &amp; prices 2026/27</h2>
      <p class="muted small">Sunday departures, 7 nights. Prices are per person and include return flights from Gatwick, transfers, chalet board with wine, and Champagne &amp; canapés. Manchester flights from £60 extra. † Partial availability — some rooms left.</p>
      {availability(c)}

      <h2 class="h-sub">Where you'll be</h2>
      <p>{esc(RESORT_COPY[c["resort"]]["intro"][0])}</p>
      <a class="link-arrow" href="{href(r["path"])}">About {esc(r["name"])}</a>
    </div>

    <aside class="chalet-aside">
      <div class="aside-card book-card">
        {from_html}
        <p class="small muted" style="margin:6px 0 16px">Including flights, transfers, chalet board &amp; wine</p>
        {f'<h6 class="mini-h">Next available weeks</h6><ul class="next-weeks">{next_weeks}</ul>' if next_weeks else '<p><strong>This chalet is fully booked for 2026/27.</strong> Call us — we often have similar options.</p>'}
        <a class="btn" href="{href("chalet-holidays/enquiry?chalet=" + c["slug"])}">Enquire about this chalet</a>
        <a class="btn btn--ghost" href="tel:{PHONE_INTL}">{icon("phone")} {PHONE}</a>
        <ul class="book-assure">
          <li>{icon("shield")}ATOL &amp; ABTOT protected</li>
          <li>{icon("plane")}Gatwick &amp; Manchester flights</li>
          <li>{icon("users")}Whole-chalet discounts available</li>
        </ul>
      </div>
    </aside>
  </div>
</div></section>

<section class="section section--stone"><div class="wrap">
  <div class="section-head"><div><span class="eyebrow">You might also like</span><h2>Similar chalets</h2></div>
  <p><a class="link-arrow" href="{href("chalet-holidays/chalet-finder")}">All {len(CHALETS)} chalets</a></p></div>
  <div class="grid grid-3">{sim}</div>
</div></section>

<section class="section section--paper"><div class="wrap">{reviews_block(3)}</div></section>
{cta_band(f"Questions about {esc(c['name'])}?", "We know every one of our chalets personally — which bedrooms get the views, which are best for children, and how far it really is to the lift. Just ask.")}

<div class="mobile-book">
  <div class="price"><small>From, per person</small><strong>{money(c["from_price"]) if c["from_price"] else "POA"}</strong></div>
  <a class="btn" href="{href("chalet-holidays/enquiry?chalet=" + c["slug"])}">Enquire</a>
  <a class="btn btn--ghost" href="tel:{PHONE_INTL}" aria-label="Call us">{icon("phone")}</a>
</div>

<div class="lightbox" hidden role="dialog" aria-modal="true" aria-label="{esc(c["name"])} photos">
  <button class="lb-close" type="button" data-lightbox-close aria-label="Close">{icon("close")}</button>
  <button class="lb-prev" type="button" data-lightbox-prev aria-label="Previous photo">‹</button>
  <div class="lb-stage">{slides}</div>
  <button class="lb-next" type="button" data-lightbox-next aria-label="Next photo">›</button>
  <div class="lb-count"></div>
</div>
'''
    cover = c["gallery"][0]["src"] if c["gallery"] else None
    desc = f"{c['name']}, {r['name']}: catered chalet sleeping {c['sleeps']}. {c['summary']}. From {money(c['from_price']) if c['from_price'] else 'POA'} pp incl. flights, transfers, food and wine."
    write_page(path, layout(path, f"{c['name']}, {r['name']} — sleeps {c['sleeps']}", desc, body, active="chalets"))


# ---------------------------------------------------------------------------
# Chalet finder
# ---------------------------------------------------------------------------
def build_finder():
    path = "chalet-holidays/chalet-finder"
    set_current(path)
    cards = []
    for c in sorted(CHALETS, key=lambda c: c["from_price"] or 99999):
        lo, hi = sleeps_range(c)
        open_dates = [iso(p["date"]) for p in c["prices"] if parse_price(p["price"])[0] != "sold"]
        flags = facility_flags(c)
        html_card = chalet_card(c)
        attrs = (f' data-min="{lo}" data-max="{hi}" data-dates="{" ".join(open_dates)}" '
                 + " ".join(f'data-{k}="{int(v)}"' for k, v in flags.items()))
        cards.append(html_card.replace("<article class=\"card\"", "<article class=\"card\"" + attrs, 1))

    dates = sorted({iso(p["date"]) for c in CHALETS for p in c["prices"]})
    date_opts = "".join(f'<option value="{d}">{dt.date.fromisoformat(d).strftime("Sun %-d %b %Y")}</option>' for d in dates)
    resort_opts = "".join(f'<option value="{k}">{esc(r["name"])}</option>' for k, r in RESORTS.items())
    guest_opts = "".join(f'<option value="{g}">{g} guests</option>' for g in ["2-6", "7-10", "11-14", "15-18", "19-25"])
    toggles = [("hottub", "Hot tub"), ("sauna", "Sauna / steam"), ("fire", "Log fire"), ("offer", "Free places offer")]
    toggle_html = "".join(f'<label class="toggle"><input type="checkbox" name="{k}" value="1"><span>{n}</span></label>' for k, n in toggles)

    body = f'''
<section class="page-head"><div class="wrap">
  {crumbs([("", "Home"), (None, "Chalet finder")])}
  <span class="eyebrow">Winter 2026/27</span>
  <h1>Find your chalet</h1>
  <p class="lead">All {len(CHALETS)} Le Ski chalets in one place. Filter by date, group size and resort — every price includes flights, transfers, catering and wine.</p>
</div></section>

<section class="section-tight" style="padding-top:32px"><div class="wrap">
  <form class="filters" id="finder" onsubmit="return false">
    <div class="filters-row">
      <label class="field"><span class="field-l">Departure</span><select name="date"><option value="">Any Sunday</option>{date_opts}</select></label>
      <label class="field"><span class="field-l">Group size</span><select name="guests"><option value="">Any size</option>{guest_opts}</select></label>
      <label class="field"><span class="field-l">Resort</span><select name="resort"><option value="">All resorts</option>{resort_opts}</select></label>
      <label class="field"><span class="field-l">Sort by</span><select name="sort"><option value="price">Price: low to high</option><option value="price-desc">Price: high to low</option><option value="size">Size: small to large</option><option value="size-desc">Size: large to small</option></select></label>
    </div>
    <div class="filters-toggles">{toggle_html}<button class="btn btn--ghost btn--sm" type="reset" id="finder-reset">Clear filters</button></div>
  </form>
  <p class="finder-count" aria-live="polite"><strong id="count">{len(CHALETS)}</strong> chalets match</p>
  <div class="grid grid-3" id="results">{"".join(cards)}</div>
  <div class="finder-empty" hidden>
    <h3>No chalets match those filters</h3>
    <p>Try another week or group size — or call us on <a href="tel:{PHONE_INTL}">{PHONE}</a>. We sometimes have rooms that aren't shown online.</p>
  </div>
</div></section>
{cta_band("Would you rather we did the searching?")}
<script>
(function () {{
  var form = document.getElementById('finder'), grid = document.getElementById('results');
  var cards = Array.prototype.slice.call(grid.children), count = document.getElementById('count');
  var empty = document.querySelector('.finder-empty');
  var params = new URLSearchParams(location.search);
  ['date', 'guests', 'resort'].forEach(function (k) {{ if (params.get(k)) form.elements[k].value = params.get(k); }});
  function apply() {{
    var f = form.elements, shown = 0;
    var g = f.guests.value ? f.guests.value.split('-').map(Number) : null;
    cards.forEach(function (c) {{
      var ok = true, d = c.dataset;
      if (f.resort.value && d.resort !== f.resort.value) ok = false;
      if (f.date.value && (' ' + d.dates + ' ').indexOf(' ' + f.date.value + ' ') < 0) ok = false;
      if (g && (+d.max < g[0] || +d.min > g[1])) ok = false;
      ['hottub', 'sauna', 'fire', 'offer'].forEach(function (k) {{ if (f[k].checked && d[k] !== '1') ok = false; }});
      c.hidden = !ok; if (ok) shown++;
    }});
    var s = f.sort.value, key = s.indexOf('size') === 0 ? 'max' : 'price', dir = s.indexOf('desc') > 0 ? -1 : 1;
    cards.slice().sort(function (a, b) {{ return dir * ((+a.dataset[key] || 99999) - (+b.dataset[key] || 99999)); }}).forEach(function (c) {{ grid.appendChild(c); }});
    count.textContent = shown; empty.hidden = shown > 0;
    var q = new URLSearchParams();
    ['date', 'guests', 'resort'].forEach(function (k) {{ if (f[k].value) q.set(k, f[k].value); }});
    history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : ''));
  }}
  form.addEventListener('change', apply);
  form.addEventListener('reset', function () {{ setTimeout(apply, 0); }});
  apply();
}})();
</script>
'''
    write_page(path, layout(path, "Chalet Finder — Search All Le Ski Chalets",
                            "Search all 36 Le Ski catered chalets in Courchevel, Val d'Isère, La Tania and Tignes by date, group size, resort and facilities.",
                            body, active="chalets"))


def build_all():
    for k in RESORTS:
        build_resort(k)
    for c in CHALETS:
        build_chalet(c)
    build_finder()


BUILDERS = [build_all]
