# Task 016: Render Natively on Mobile Phones

**Status:** Done

## Objective

Make every page usable and native-feeling on a phone (≈390px wide, iPhone / Android) without changing the desktop web experience.

## Approach

- **One phone stylesheet in `base.html`**, scoped to `@media (max-width: 640px)` and loaded *after* each page's `extra_css`, so it wins on phones only and desktop CSS is untouched:
  - Edge-to-edge card (no body padding / rounded card / shadow), safe-area insets (`viewport-fit=cover`).
  - Inputs/selects/textareas at 16px so iOS doesn't zoom in on focus.
  - Media (`img`/`iframe`/`video`/`canvas`) capped at 100% width; tables scroll sideways inside themselves.
  - Fixed `.toggle-sidebar` buttons (Answers / Questions / Details) go into the page flow instead of overlapping titles.
  - `.timer-display` becomes sticky at the top-right so it stays visible while scrolling without covering answer buttons.
  - No hover-scale on touch devices (`@media (hover: none)`).
- **"Open PDF full screen" button** (script in `base.html`, phones only): phone browsers can't page through a PDF inside an iframe (iOS shows page 1, Android shows nothing), so a button linking to the PDF is inserted above every PDF iframe, including ones whose `src` is set later.
- **Add to Home Screen:** `/manifest.webmanifest` route (standalone display, theme colour), `static/icon-192.png`, `static/icon-512.png`, `static/apple-touch-icon.png`, Apple/Android web-app meta tags.
- **App top bar (phones):** sticky frosted bar on every logged-in page — `‹ Back` on the left reuses the page's own `← …` link (label shortened, e.g. `‹ Dashboard`; hidden on the account's home screen), the page title fades into the bar once the page heading scrolls away, account menu (name, Home, Logout) on the right replaces the `username (role) Logout` line. z-index 50: above page content, below modals/toasts.
- **Touch feel (phones):** buttons, chips, selects and inputs at least 44px tall, press-down feedback, no double-tap zoom delay (`touch-action: manipulation`), no text selection on controls, 22px checkboxes/radios.
- **Per-page phone fixes:** parent dashboard tabs scroll sideways instead of clipping; Words add-word row wraps; Materials article cards and source filter wrap; Settings form rows stack; live reading session panels fit the screen; math test / math review / science test scroll with the page instead of inside fixed-height boxes.

## Verification (2026-10-12)

Seeded copy of the DB, Playwright at 1280px (desktop), 768px (tablet) and iPhone 13 (Chromium + WebKit):
- Desktop: 48/49 pages, 9 modals and 11 plan/math-bank add panels pixel-identical before vs after (the one diff is the vocab test's random question type).
- Phone: 0 pages with horizontal overflow (before: Words, Materials); no JS errors in WebKit; modals and add panels fit.
- Tablet: no overflow.
- App bar + touch layer (WebKit iPhone): back links resolve to the page's own back destination on 11 sampled pages and navigate correctly; title appears on scroll; menu opens; modals dim the bar; desktop still identical (only diffs: random vocab question type, live RSS feed content).
