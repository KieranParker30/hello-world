from lib import *


def build_home():
    set_current("")
    featured = [chalet_by_slug(s) for s in (
        "chalet-mistral-courchevel", "chalet-azel-val-d-isere", "chalet-michele-courchevel-la-tania",
        "chalet-rikiki-courchevel", "chalet-genevieve-val-d-isere", "chalet-le-corty-courchevel-la-tania")]

    resort_tiles = "".join(f'''
<a class="tile reveal" href="{href(r["path"])}">
  {img(r["hero"], r["name"], sizes="(max-width: 720px) 100vw, (max-width: 980px) 50vw, 25vw", w=800)}
  <div class="tile-body">
    <h3>{esc(r["name"])}</h3>
    <p>{esc(r["blurb"])}</p>
    <div class="tile-stats"><span><b>{len(r["chalets"])}</b> chalet{"s" if len(r["chalets"]) != 1 else ""}</span><span><b>{r["altitude"]}</b></span><span>from <b>{money(r["from"])}</b></span></div>
  </div>
</a>''' for r in RESORTS.values())

    included = [
        ("plane", "Our own Sunday flights", "Gatwick or Manchester to Chambéry with 22kg hold bag included — the closest airport to the Alps, on the quietest day to travel."),
        ("bus", "Direct transfers", "Our own coaches meet you at arrivals. La Tania in 80 minutes, Courchevel in 90, Val d'Isère and Tignes in two hours."),
        ("chef", "Proper chalet catering", "Cooked breakfast, afternoon tea and a three-course dinner five nights a week, made fresh by your chalet host."),
        ("wine", "Wine with dinner", "Unlimited house wine at dinner, with coffee and mints, plus a cheeseboard once a week."),
        ("glass", "Champagne & canapés", "Champagne and canapés on your first and last nights, and local Méthode Champenoise on the evenings between."),
        ("users", "A team in resort", "A Guest Services Manager to book restaurants, lift passes, lessons and hire — so you don't have to."),
    ]
    inc_html = "".join(f'<div>{icon(i)}<h3>{t}</h3><p>{d}</p></div>' for i, t, d in included)

    dates = "".join(
        f'<a class="date-card" href="{href(p)}"><small>{d}</small><strong>{esc(n)}</strong><span class="link-arrow">See availability</span></a>'
        for p, n, d in HOLIDAYS)

    body = f'''
{hero("Scarlottas-chalet-exteriors-Le-Ski-Courchevel.jpg",
      "Catered ski chalets, <em>looked after</em> properly",
      "36 hand-picked chalets in Courchevel, Val d'Isère, La Tania and Tignes — with our own flights, transfers and chalet teams. Family run since 1982, and still answering the phone ourselves.",
      eyebrow="Le Ski · Winter 2026/27", extra=search_panel(), alt="A Le Ski chalet in fresh snow, Courchevel")}
{trustbar()}

<section class="section"><div class="wrap">
  <div class="section-head">
    <div><span class="eyebrow">Our resorts</span><h2>Four snowsure resorts, known <em>inside out</em></h2></div>
    <p>We could offer fifty resorts. We choose to offer four, so our team knows every lift, every restaurant terrace and every short cut home.</p>
  </div>
  <div class="grid grid-4">{resort_tiles}</div>
</div></section>

<section class="section section--paper"><div class="wrap">
  <div class="section-head">
    <div><span class="eyebrow">Chalets for 2026/27</span><h2>Over 70% booked for next winter</h2></div>
    <p>From a private chalet for two to Rikiki for 22, every chalet has the same food, wine and service — so the price simply reflects the chalet and its position. <a class="link-arrow" href="{href("chalet-holidays/chalet-finder")}">Browse all {len(CHALETS)} chalets</a></p>
  </div>
  <div class="grid grid-3">{"".join(chalet_card(c) for c in featured)}</div>
</div></section>

<section class="section section--petrol"><div class="wrap">
  <div class="section-head">
    <div><span class="eyebrow">One price, all of this</span><h2>Everything taken care of, door to door</h2></div>
    <p style="color:#B9CDD4">Our prices include flights, transfers, catering and wine. No hidden charges, no tiered service levels — what we describe is what you get. <a class="link-arrow" style="color:#fff" href="{href("chalet-holidays/included")}">What's included</a></p>
  </div>
  <div class="included">{inc_html}</div>
</div></section>

<section class="section"><div class="wrap">
  <div class="split">
    <div class="split-media reveal">
      {img("cJontyWilde_LESKI_PEOPLE_16.12.23-2317407_DSF2317_1.jpg", "A Le Ski chalet host laying the dinner table", sizes="(max-width: 980px) 100vw, 50vw")}
      <div class="float-note"><strong>“Sarah was our host five years ago — what a lovely surprise to see her again.”</strong>Lindsay, La Tania</div>
    </div>
    <div>
      <span class="eyebrow">From greeting to goodbye</span>
      <h2>Our people make the difference</h2>
      <p class="lead">We treat your week in the mountains as if it were our own. Fancy a chalet with a hot tub? Sorted. A special diet? No problem. A birthday cake on Wednesday? Leave it with us.</p>
      <div class="pillars" style="grid-template-columns:1fr 1fr;margin:36px 0">
        <div class="pillar"><span class="num">01</span><h3>With you all the way</h3><p>We help you choose the right chalet, fly you there and drive you up the mountain.</p></div>
        <div class="pillar"><span class="num">02</span><h3>Little details</h3><p>Freshly baked afternoon tea, ski passes sorted, restaurant tables booked.</p></div>
      </div>
      <div class="btn-row"><a class="btn" href="{href("chalet-holidays/staff")}">Meet our teams</a><a class="btn btn--ghost" href="{href("chalet-holidays")}">Our story</a></div>
    </div>
  </div>
</div></section>

<section class="section section--stone"><div class="wrap">
  <div class="split split--rev">
    <div class="split-media split-media--wide reveal">{img("Cheese_and_wine.jpg", "Cheese board and red wine by the chalet fire", sizes="(max-width: 980px) 100vw, 50vw")}</div>
    <div>
      <span class="eyebrow">Food &amp; wine</span>
      <h2>Dinner is the best bit of the day</h2>
      <p class="lead">Three courses cooked from scratch, wine poured generously, and a fire going in the grate. Our hosts are trained on our own menus before the season starts, and special diets are handled with care.</p>
      <div class="btn-row" style="margin-top:28px"><a class="btn" href="{href("chalet-holidays/food")}">Sample menus</a><a class="btn btn--ghost" href="{href("chalet-holidays/special-diets")}">Special diets</a></div>
    </div>
  </div>
</div></section>

<section class="section"><div class="wrap">
  <div class="section-head">
    <div><span class="eyebrow">School holidays</span><h2>Book the busy weeks early</h2></div>
    <p>Our flights are chartered to match our beds, so peak weeks sell first. Families: see our <a href="{href("chalet-holidays/family")}">family skiing</a> guide.</p>
  </div>
  <div class="dates">{dates}</div>
</div></section>

<section class="section section--paper"><div class="wrap">{reviews_block(3)}</div></section>

<section class="section"><div class="wrap">
  <div class="stats">
    <div class="stat"><strong>1982</strong><span>The year we took our first guests skiing</span></div>
    <div class="stat"><strong>43rd</strong><span>Season in the French Alps</span></div>
    <div class="stat"><strong>184 yrs</strong><span>Combined Le Ski experience in our UK office</span></div>
    <div class="stat"><strong>100%</strong><span>Financial protection — ATOL &amp; ABTOT</span></div>
  </div>
</div></section>

{cta_band()}
'''
    write_page("", layout("", "Catered Ski Chalets in Courchevel, Val d'Isère, La Tania & Tignes | Le Ski",
                          "Family-owned catered chalet holidays since 1982. 36 chalets in Courchevel, Val d'Isère, La Tania and Tignes with our own flights, transfers and chalet teams.",
                          body))
