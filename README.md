# Le Ski — website redesign

A full redesign of [leski.com](https://www.leski.com): 86 pages, generated as a static site in `site/`.

## Brief & approach

- **Audience:** UK families, groups of friends and long-standing repeat guests — mostly 35–65, time-poor, valuing reassurance and personal service over flashiness.
- **Tone:** professional yet modern. Editorial serif headlines (Fraunces) with a clean sans (Inter), real photography first, generous white space.
- **Brand continuity:** keeps the existing logo and its petrol `#134C65` / mint `#69C0B0` palette, with warm alpine neutrals.
- **Trust up front:** ATOL/ABTOT protection, family-owned since 1982, phone number and "a human answers" are visible on every page.
- **Conversion:** search panel → chalet finder with live filters (date, group size, resort, hot tub, sauna, offers); every chalet page shows availability by week, a sticky price/enquire card (a bottom bar on mobile), and pre-fills the enquiry form.

## Structure

| Path | What |
|---|---|
| `src/build.py` | Builds every page into `site/` |
| `src/lib.py` | Layout, header/mega-menu, footer, shared components |
| `src/pages_home.py` | Homepage |
| `src/pages_chalets.py` | Resort overviews, 36 chalet pages, chalet finder |
| `src/pages_content.py` | Markdown engine for content pages, forms |
| `src/content/**.md` | Copy for 45 content pages (URLs match the live site) |
| `src/data/chalets.json` | Chalet data and 2026/27 prices extracted from the live site |
| `src/fetch_images.py` | Downloads referenced photos and writes 800/1600px WebP |
| `site/assets/` | CSS, JS, logo and optimised images |

## Build

```sh
python3 src/build.py          # regenerate HTML
python3 src/fetch_images.py   # fetch/convert any new images (needs Pillow)
python3 -m http.server -d site 8000
```

URLs mirror the current site so existing SEO and inbound links carry over. Forms are front-end only and need connecting to the booking system/CRM on launch.
