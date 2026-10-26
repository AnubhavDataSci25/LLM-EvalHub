# LLM-EvalHub: Design System

This document records the **current** frontend design and theme. **Do not change the visual identity**: beige and olive green, Source Serif 4, light and dark mode. New work must conform to it.

> **Source of truth:** the CSS variables in `frontend/src/index.css` and the mapping in `frontend/tailwind.config.js`. Hex values below are the palette used across the product and its presentation material; if they differ from `index.css`, `index.css` wins, and this file should be corrected.

---

## 1. Design principles

1. **Evidence first.** Numbers, labels and provenance are more important than decoration.
2. **Calm, technical, premium.** A developer-SaaS feel: generous spacing, clear hierarchy, restrained colour.
3. **Honest states.** Unavailable is shown as unavailable ("n/a" plus reason), never as zero.
4. **One accent.** Olive green carries interaction and emphasis; semantic colours are reserved for pass, warn and fail.
5. **Consistency over novelty.** Reuse primitives from `components/ui` and `components/charts`.
6. **Accessible by default.** Contrast, focus rings, keyboard reach, reduced motion.

## 2. Colour

Colours are CSS variable tokens. Components use tokens through Tailwind, never raw hex.

### Light mode (beige)

| Role | Value | Use |
|---|---|---|
| Background | beige `#F5F0E4` | App background |
| Surface | lighter beige, near-white warm | Cards, panels, tables |
| Text | dark brown-black `#2F2921` | Body and headings |
| Muted text | softened brown | Secondary labels |
| Border | warm sand | Dividers, card outlines |
| Accent (primary) | olive `#4A562C` | Primary buttons, active nav, links |
| Accent (secondary) | olive `#7C8C46` | Highlights, chart series, hover |

### Dark mode

Activated by the `.dark` class on the root element (via `useTheme`). The same token names are redefined: a deep warm-dark olive/charcoal background, slightly raised surfaces (lighter than the background), light beige text, and a lightened olive accent for contrast.

### Semantic colours

| Meaning | Use |
|---|---|
| Success | Passing metrics, available providers |
| Warning | Rate-limited, low-confidence, caveats |
| Danger | Failures, errors, destructive actions |
| Info | Neutral notices |

Each has a text colour and a soft tinted background for badges. Tailwind opacity modifiers must be valid steps (for example `/20`).

## 3. Typography

| Item | Rule |
|---|---|
| Family | **Source Serif 4** everywhere: headings, body, labels, tables, buttons |
| Fallback | Georgia, then generic serif, used only when the font fails to load |
| Numbers | Use tabular figures in tables and metric cards for alignment |
| Scale | Display for landing hero; H1 page title; H2 section; H3 card title; body; small for captions and badges |
| Weight | Regular for body, semibold for headings, avoid more than two weights per view |
| Line length | Keep body text within roughly 65 to 75 characters |

## 4. Layout and spacing

- App shell: `AppLayout` with sidebar navigation and top bar (theme toggle, status).
- Spacing follows a consistent 4 px scale; sections separated by generous vertical rhythm.
- Content is responsive: sidebar collapses on small screens; tables scroll horizontally inside their card, not the page.
- Cards: rounded corners, subtle border, very soft shadow. Avoid heavy shadows.
- Maximum content width on wide screens to keep reading comfortable.

## 5. Components (in `components/ui`)

| Component | Notes |
|---|---|
| Button | Primary (olive), secondary (outline), ghost, danger; loading state with spinner |
| Card / Panel | Standard container with optional header and actions |
| MetricCard | Label, value, delta, and kind badge; "n/a" state with reason |
| Badge | Status (available, rate-limited, failed), metric kind (deterministic, llm_judge, measured), difficulty, category |
| Table | Sticky header option, sortable columns, row hover, empty state |
| Tabs | Used on detail pages (overview, cases, failures, RAG) |
| Progress | Run progress with counts |
| Input, Select, Textarea, Toggle, Slider | Consistent focus ring in the accent colour |
| Modal / Confirm | For destructive actions and cost estimates |
| EmptyState | Icon, one-sentence explanation, one clear action |
| ErrorState | Plain-language error, retry action |
| Skeleton | Shown while loading, matching the final layout |
| Toast | Brief feedback after actions |

Icons come from **Lucide React**, with consistent size and stroke weight.

## 6. Charts (Recharts, in `components/charts`)

| Chart | Purpose |
|---|---|
| Grouped bar / radar | Model comparison across metrics |
| Line | Metric trends across experiments |
| Pie or donut / bar | Failure category distribution |
| Delta bar | Before vs after experiment change |
| Bar / box-style | Latency comparison |

Rules:
1. Colours come from the theme tokens; use the olive scale plus restrained neutrals for series, semantic colours only for pass/fail meaning.
2. Never rely on colour alone; add labels, patterns or direct value labels.
3. Unavailable data is omitted with a note, never drawn as zero.
4. Tooltips show the exact value, unit and, where relevant, sample size.
5. Axis labels include units (ms, score 0 to 1).
6. Charts must read correctly in both light and dark mode.

## 7. Motion

- Library: Framer Motion, plus CSS transitions for hover and focus.
- Use subtle entrance fades and short slides for page content, staggered list reveals, animated number counts for KPIs.
- Durations short (roughly 150 to 350 ms), easing smooth, no looping decorative animation.
- **Smooth scrolling** is enabled globally.
- Respect `prefers-reduced-motion`: disable or minimise animation.

## 8. Page patterns

| Page type | Pattern |
|---|---|
| Dashboard | KPI row, then chart grid, then recent activity |
| List pages (datasets, experiments, reports, failures) | Header with primary action, filters, table, pagination, empty state |
| Detail pages | Summary header, tabs, evidence panels |
| Compare | Side-by-side columns with delta highlighting |
| Failure detail | Question, expected vs generated answer, retrieved context, config, scores, category, diagnosis |
| New evaluation | Stepwise form: dataset, models, metrics (with kind labels), parameters, confirm |
| Settings | Provider cards showing configured status (never key values) |
| Landing | Hero with the core loop, short feature highlights, call to action |

## 9. Content and microcopy

- Plain, direct language. State what happened and what to do next.
- Provider errors: say the cause (rate limit, bad key, model unavailable) and a next step.
- Always show metric kind and, when relevant, why a value is unavailable.
- Avoid claims like "best model"; use "highest score under this profile".

## 10. Accessibility checklist

- [ ] Text contrast meets WCAG AA in both modes.
- [ ] Visible focus ring on all interactive elements.
- [ ] Interactive controls reachable by keyboard; modals trap focus.
- [ ] Icons that convey meaning have text or aria labels.
- [ ] Charts have text alternatives or accompanying tables.
- [ ] Reduced-motion preference respected.

## 11. Rules for changes

1. Use tokens and existing primitives; do not introduce new colours or fonts.
2. Any new component must support light and dark mode, loading, empty and error states.
3. Check both themes before declaring a UI change complete.
4. If a theme change is ever requested, change tokens only in `index.css` and verify contrast in both modes.
