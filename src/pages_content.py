"""Editorial/content pages, written as lightweight Markdown in src/content/**.md.

Front matter (key: value lines between --- fences):
  title, description, h1 (HTML allowed), eyebrow, lead, hero (image), nav (active menu key),
  parent (path|Label for breadcrumbs), related (comma-separated paths), toc (no to hide),
  date (ISO Sunday: lists chalets with availability that week), layout (wide = no sidebars)

Body syntax (on top of headings, paragraphs, lists, **bold**, *em*, [links](path)):
  ::: callout ... :::            highlighted box
  ??? Question                   accordion item; answer is the following lines up to a blank line
  ![alt](image.jpg)              figure (images come from the original site's photo library)
  ![alt](a.jpg|b.jpg)            two-up gallery
  | a | b |                      table (first row = header)
  [[chalets:date=YYYY-MM-DD]]    chalet cards available that week
  [[chalets:slugs=a,b,c]]        specific chalet cards
  [[form:enquiry]] / [[form:contact]]
  [[reviews]]
"""
import datetime as dt
import re

from lib import *
from pages_chalets import iso, parse_price

CONTENT = Path(__file__).parent / "content"

TITLES = {}  # path -> short title, filled before rendering so related links have names


def parse_file(f):
    text = f.read_text()
    meta, body = {}, text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    rel = f.relative_to(CONTENT).with_suffix("")
    path = str(rel).replace("\\", "/")
    if path.endswith("/index"):
        path = path[:-6]
    return path, meta, body.strip()


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", s).lower()).strip("-")


def inline(s):
    s = esc(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)

    def link(m):
        text, target = m.group(1), m.group(2)
        if target.startswith(("http", "mailto:", "tel:", "#")):
            ext = ' rel="noopener"' if target.startswith("http") else ""
            return f'<a href="{target}"{ext}>{text}</a>'
        return f'<a href="{href(target)}">{text}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    return s


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------
def chalets_on(date_iso):
    out = []
    for c in CHALETS:
        for p in c["prices"]:
            if iso(p["date"]) == date_iso:
                status, amount, _ = parse_price(p["price"])
                if status != "sold":
                    out.append((amount or 99999, c))
    return [c for _, c in sorted(out, key=lambda x: x[0])]


def directive(name, arg):
    if name == "chalets":
        k, _, v = arg.partition("=")
        if k == "date":
            cs = chalets_on(v)
            if not cs:
                return f'<div class="callout"><p>Every chalet is currently booked for this week. Call us on <a href="tel:{PHONE_INTL}">{PHONE}</a> — cancellations do come up.</p></div>'
            day = dt.date.fromisoformat(v).strftime("%A %-d %B %Y")
            more = f'<p class="mt-l"><a class="btn btn--ghost" href="{href("chalet-holidays/chalet-finder?date=" + v)}">See all {len(cs)} in the chalet finder</a></p>' if len(cs) > 6 else ""
            return (f'<p class="muted small"><strong>{len(cs)} chalets</strong> still have space for departure on {day}. Prices are per person and include flights.</p>'
                    f'<div class="grid grid-2 content-cards">{"".join(chalet_card(c, "(max-width: 720px) 100vw, 33vw") for c in cs[:6])}</div>{more}')
        if k == "slugs":
            cs = [chalet_by_slug(s.strip()) for s in v.split(",")]
            return f'<div class="grid grid-2 content-cards">{"".join(chalet_card(c, "(max-width: 720px) 100vw, 33vw") for c in cs)}</div>'
        if k == "filter":
            from pages_chalets import facility_flags
            cs = [c for c in CHALETS if facility_flags(c).get(v)]
            cs.sort(key=lambda c: c["from_price"] or 99999)
            return f'<div class="grid grid-2 content-cards">{"".join(chalet_card(c, "(max-width: 720px) 100vw, 33vw") for c in cs[:6])}</div>'
    if name == "reviews":
        n = len(REVIEWS) if arg == "all" else 3
        cls = "reviews reviews--grid" if arg == "all" else "reviews reviews--content"
        return reviews_block(n, head=False).replace('class="reviews"', f'class="{cls}"')
    if name == "posts":
        cards = []
        for p, title, cat, blurb, image in POSTS:
            link = href(p) if not p.startswith("http") else p
            cards.append(f'<article class="card"><div class="card-media">{img(image, title, sizes="(max-width: 720px) 100vw, 33vw", w=800)}</div>'
                         f'<div class="card-body"><div class="card-meta"><span>{esc(cat)}</span></div><h3><a href="{link}">{esc(title)}</a></h3><p>{esc(blurb)}</p>'
                         f'<div class="card-foot"><span class="link-arrow">Read</span></div></div></article>')
        return f'<div class="grid grid-3">{"".join(cards)}</div>'

    if name == "form":
        return FORMS[arg]()
    if name == "resorts":
        return '<div class="grid grid-2 content-cards">' + "".join(
            f'<a class="tile tile--short" href="{href(r["path"])}">{img(r["hero"], r["name"], sizes="(max-width: 720px) 100vw, 33vw", w=800)}<div class="tile-body"><h3>{esc(r["name"])}</h3><p>{esc(r["blurb"])}</p></div></a>'
            for r in RESORTS.values()) + "</div>"
    raise ValueError(f"unknown directive {name}:{arg}")


# ---------------------------------------------------------------------------
# Markdown → HTML
# ---------------------------------------------------------------------------
def render(md):
    lines = md.splitlines()
    out, toc = [], []
    i = 0
    para = []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            flush(); i += 1; continue
        if s.startswith("## "):
            flush()
            t = s[3:]
            hid = slugify(t)
            toc.append((hid, re.sub(r"<[^>]+>", "", t)))
            out.append(f'<h2 id="{hid}">{inline(t)}</h2>')
        elif s.startswith("### "):
            flush(); out.append(f"<h3>{inline(s[4:])}</h3>")
        elif s.startswith("::: "):
            flush()
            kind = s[4:].strip()
            j = i + 1
            buf = []
            while j < len(lines) and lines[j].strip() != ":::":
                buf.append(lines[j]); j += 1
            inner, _ = render("\n".join(buf))
            out.append(f'<div class="{kind}">{inner}</div>')
            i = j
        elif s.startswith("??? "):
            flush()
            items = []
            while i < len(lines) and lines[i].strip().startswith("??? "):
                q = lines[i].strip()[4:]
                j = i + 1
                buf = []
                while j < len(lines) and lines[j].strip() and not lines[j].strip().startswith("??? "):
                    buf.append(lines[j]); j += 1
                ans, _ = render("\n".join(buf))
                items.append(f'<details><summary>{inline(q)}</summary><div class="acc-body">{ans}</div></details>')
                i = j
                while i < len(lines) and not lines[i].strip():
                    i += 1
            out.append(f'<div class="accordion">{"".join(items)}</div>')
            continue
        elif s.startswith("[[") and s.endswith("]]"):
            flush()
            name, _, arg = s[2:-2].partition(":")
            out.append(directive(name, arg))
        elif s.startswith("!["):
            flush()
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
            alt, srcs = m.group(1), m.group(2).split("|")
            if len(srcs) == 1:
                out.append(f'<figure>{img(srcs[0], alt, sizes="(max-width: 980px) 100vw, 60vw")}{f"<figcaption>{esc(alt)}</figcaption>" if alt else ""}</figure>')
            else:
                out.append('<div class="gallery-2">' + "".join(img(x, alt, sizes="(max-width: 720px) 100vw, 30vw", w=800) for x in srcs) + "</div>")
        elif s.startswith("> "):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip()); i += 1
            cite = ""
            if buf and buf[-1].startswith("— "):
                cite = f"<cite>{inline(buf.pop()[2:])}</cite>"
            out.append(f"<blockquote><p>{inline(' '.join(buf))}</p>{cite}</blockquote>")
            continue
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            continue
        elif re.match(r"^[-*] ", s):
            flush()
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i].strip()):
                items.append(f"<li>{inline(lines[i].strip()[2:])}</li>"); i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue
        elif re.match(r"^\d+\. ", s):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i].strip()):
                items.append(f"<li>{inline(re.sub(r'^\d+\. ', '', lines[i].strip()))}</li>"); i += 1
            out.append(f"<ol>{''.join(items)}</ol>")
            continue
        elif s.startswith("<"):
            flush(); out.append(s)
        else:
            para.append(s)
        i += 1
    flush()
    return "\n".join(out), toc


# ---------------------------------------------------------------------------
# Forms (front-end only; wire to the booking system / CRM on launch)
# ---------------------------------------------------------------------------
def _date_options():
    dates = sorted({iso(p["date"]) for c in CHALETS for p in c["prices"]})
    return "".join(f'<option value="{d}">{dt.date.fromisoformat(d).strftime("Sunday %-d %B %Y")}</option>' for d in dates)


def form_enquiry():
    chalet_opts = "".join(f'<option value="{c["slug"]}">{esc(c["name"])} — {esc(RESORTS[c["resort"]]["name"])} (sleeps {esc(c["sleeps"])})</option>'
                          for c in sorted(CHALETS, key=lambda c: (c["resort"], c["name"])))
    return f'''
<form class="form enquiry-form" id="enquiry" novalidate>
  <fieldset><legend>Your holiday</legend>
    <div class="form-row">
      <div class="field"><label for="f-date">Departure date</label><select id="f-date" name="date"><option value="">Not sure yet</option>{_date_options()}</select></div>
      <div class="field"><label for="f-chalet">Chalet</label><select id="f-chalet" name="chalet"><option value="">Please suggest some</option>{chalet_opts}</select></div>
    </div>
    <div class="form-row">
      <div class="field"><label for="f-adults">Adults</label><input id="f-adults" name="adults" type="number" min="1" max="30" value="2" inputmode="numeric"></div>
      <div class="field"><label for="f-children">Children (under 18)</label><input id="f-children" name="children" type="number" min="0" max="20" value="0" inputmode="numeric"></div>
    </div>
    <div class="form-row">
      <div class="field"><label for="f-airport">Flying from</label><select id="f-airport" name="airport"><option>London Gatwick</option><option>Manchester (+£60pp)</option><option>Making my own way</option></select></div>
      <div class="field"><label for="f-resort">Preferred resort</label><select id="f-resort" name="resort"><option value="">No preference</option>{"".join(f'<option value="{k}">{esc(r["name"])}</option>' for k, r in RESORTS.items())}</select></div>
    </div>
  </fieldset>
  <fieldset><legend>About you</legend>
    <div class="form-row">
      <div class="field"><label for="f-name">Full name</label><input id="f-name" name="name" autocomplete="name" required></div>
      <div class="field"><label for="f-phone">Phone</label><input id="f-phone" name="phone" type="tel" autocomplete="tel"></div>
    </div>
    <div class="field"><label for="f-email">Email</label><input id="f-email" name="email" type="email" autocomplete="email" required></div>
    <div class="field"><label for="f-msg">Anything else?</label><textarea id="f-msg" name="message" placeholder="Special diets, celebrations, ski lessons, ages of children…"></textarea></div>
    <label class="check"><input type="checkbox" name="optin"> Send me snow news and early-booking offers (no more than once a month).</label>
  </fieldset>
  <button class="btn" type="submit">Send enquiry {icon("arrow")}</button>
  <p class="small muted">We reply within one working day — usually much sooner. Your details are handled in line with our <a href="{href("chalet-holidays/privacy-policy")}">privacy policy</a>.</p>
  <div class="form-success" hidden><h3>Thank you — we've got it.</h3><p>One of our UK team will be in touch within one working day. If it's urgent, call <a href="tel:{PHONE_INTL}">{PHONE}</a>.</p></div>
</form>
<script>
(function () {{
  var f = document.getElementById('enquiry'), q = new URLSearchParams(location.search);
  ['date', 'chalet', 'resort'].forEach(function (k) {{ if (q.get(k) && f.elements[k]) f.elements[k].value = q.get(k); }});
  if (q.get('waitlist')) f.elements.message.value = 'Please add me to the waiting list for this week.';
  f.addEventListener('submit', function (e) {{
    e.preventDefault();
    if (!f.checkValidity()) {{ f.reportValidity(); return; }}
    f.querySelectorAll('fieldset, button[type=submit]').forEach(function (el) {{ el.hidden = true; }});
    f.querySelector('.form-success').hidden = false;
    f.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
}})();
</script>'''


def form_contact():
    return f'''
<form class="form" id="contact" novalidate onsubmit="event.preventDefault();if(!this.checkValidity()){{this.reportValidity();return}}this.innerHTML='<div class=&quot;callout&quot;><h3>Thank you</h3><p>We\\'ll reply within one working day.</p></div>'">
  <div class="form-row">
    <div class="field"><label for="c-name">Name</label><input id="c-name" name="name" autocomplete="name" required></div>
    <div class="field"><label for="c-email">Email</label><input id="c-email" name="email" type="email" autocomplete="email" required></div>
  </div>
  <div class="field"><label for="c-ref">Booking reference <span class="muted">(if you have one)</span></label><input id="c-ref" name="ref"></div>
  <div class="field"><label for="c-msg">Message</label><textarea id="c-msg" name="message" required></textarea></div>
  <button class="btn" type="submit">Send message</button>
</form>'''


FORMS = {"enquiry": form_enquiry, "contact": form_contact}

LIVE = "https://www.leski.com/blog/"
POSTS = [
    (LIVE + "le_ski_latest/Belated_Yorkshire_Day", "Happy belated Yorkshire Day!", "Le Ski latest",
     "Apologies to all Yorkshire folk — at 60% full already for this winter, we've been a bit busy.", "Roving_reporter.jpg"),
    (LIVE + "holiday_advice/things-to-do-in-courchevel", "Things to do in Courchevel: a complete guide", "Holiday advice",
     "600km of pistes in Les 3 Vallées — and plenty more to do off them.", "IMG_1413.jpg"),
    (LIVE + "holiday_advice/lessons-val-slopes", "Ski lessons in Val d'Isère: from booking to the slopes", "Holiday advice",
     "Your step-by-step guide, from booking a lesson to clicking into your skis.", "Cours_de_ski-7096-1200px.jpg"),
    (LIVE + "holiday_advice/private-group-ski-lessons", "Private vs group lessons in Val d'Isère", "Holiday advice",
     "Which should you choose? We weigh up the pros and cons.", "AL_NEW_GEN_7324002-min.jpg"),
    (LIVE + "holiday_advice/childrens-lessons-la-tania", "Children's lessons in La Tania: are they worth it?", "Holiday advice",
     "The value of children's ski lessons in La Tania.", "LAT-bubble-B_1.jpg"),
    ("blog/holiday_advice/Courchevel_Aquamotion_guide", "Our guide to Aquamotion, Courchevel", "Holiday advice",
     "Pools, slides, a surf wave, a salt cave and spa — everything you need to know.", "AL_25111150-Aquamotion-Surf_Board_paysage_resized_1.jpg"),
]


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------
def build_content_page(path, meta, md):
    set_current(path)
    body_html, toc = render(md)
    title = meta.get("title", "")
    h1 = meta.get("h1", esc(title))
    lead = meta.get("lead", "")
    trail = [("", "Home")]
    if meta.get("parent"):
        p, _, label = meta["parent"].partition("|")
        if p != path:
            trail.append((p, label))
    trail.append((None, re.sub(r"<[^>]+>", "", meta.get("short", title))))

    if meta.get("hero"):
        top = hero(meta["hero"], h1, inline(lead) if lead else "", eyebrow=meta.get("eyebrow", ""), cls="hero--short", trail=trail, alt=title)
    else:
        top = f'''<section class="page-head"><div class="wrap">{crumbs(trail)}
{f'<span class="eyebrow">{meta["eyebrow"]}</span>' if meta.get("eyebrow") else ""}<h1>{h1}</h1>{f'<p class="lead">{inline(lead)}</p>' if lead else ""}</div></section>'''

    related = [p.strip() for p in meta.get("related", "").split(",") if p.strip()]
    rel_html = "".join(f'<li><a href="{href(p)}">{esc(TITLES.get(p, p))}</a></li>' for p in related)
    show_toc = meta.get("toc", "yes") != "no" and len(toc) >= 3
    toc_html = ("<nav class=\"toc\" aria-label=\"On this page\"><h6>On this page</h6><ol>"
                + "".join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc) + "</ol></nav>") if show_toc else "<div></div>"
    aside = f'''<aside class="aside">
  <div class="aside-card aside-card--petrol">
    <h4>Talk to our UK team</h4>
    <p>Real people in Huddersfield who've skied every resort we offer.</p>
    <a class="btn btn--mint" href="tel:{PHONE_INTL}">{icon("phone")} {PHONE}</a>
    <a class="btn btn--light" href="{href("chalet-holidays/enquiry")}">Make an enquiry</a>
  </div>
  {f'<div class="aside-card"><h4>Related</h4><ul>{rel_html}</ul></div>' if rel_html else ""}
</aside>'''

    if meta.get("layout") == "wide":
        main = f'<section class="section-tight"><div class="wrap"><div class="prose prose--wide">{body_html}</div></div></section>'
    elif meta.get("layout") == "narrow":
        main = f'<section class="section-tight"><div class="wrap-narrow"><div class="prose">{body_html}</div></div></section>'
    else:
        cls = "article" if show_toc else "article article--no-toc"
        main = f'<section class="section-tight"><div class="wrap"><div class="{cls}">{toc_html if show_toc else ""}<div class="prose">{body_html}</div>{aside}</div></div></section>'

    page = top + main + (cta_band() if meta.get("cta", "yes") != "no" else "")
    write_page(path, layout(path, title, meta.get("description", lead[:155]), page, active=meta.get("nav", "")))


def build_all_content():
    pages = [parse_file(f) for f in sorted(CONTENT.rglob("*.md"))]
    for _, _, groups in NAV:
        for _, links in groups or []:
            for p, n in links:
                TITLES[p] = n
    for path, meta, _ in pages:
        TITLES.setdefault(path, meta.get("short", meta.get("title", path)))
    for r in RESORTS.values():
        TITLES.setdefault(r["path"], r["name"])
    TITLES.setdefault("chalet-holidays/chalet-finder", "Chalet finder")
    for path, meta, md in pages:
        build_content_page(path, meta, md)


BUILDERS = [build_all_content]
