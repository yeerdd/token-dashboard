# Light Background Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the token dashboard's existing light landing page and dashboard shell into a faithful, accessible Background Paths-inspired experience without changing data behavior.

**Architecture:** Keep the single-file frontend architecture. CSS will define the light visual tokens, path layering, landing transition, and reduced-motion behavior; existing JavaScript will retain its API rendering path while making generated SVG paths deterministic and accessibility-aware. Python API and collectors remain untouched.

**Tech Stack:** HTML, CSS, vanilla JavaScript, SVG, ECharts 5, Python standard-library HTTP server.

## Global Constraints

- Modify only `projects/token-dashboard/index.html` for application behavior and appearance.
- Preserve `/api/data`, the data model, 5-second refresh cadence, and all ECharts data rendering.
- Do not copy the reference template's source, copy, or assets.
- Keep the palette fixed to `#FFFFFF`, `#F8FAFC`, `#0F172A`, `#64748B`, `#475569`, `#CBD5E1`, and `#0D9488`.
- Ensure keyboard focus, mobile layout, and reduced-motion behavior remain usable.

---

### Task 1: Refine the light visual shell and landing transition

**Files:**
- Modify: `projects/token-dashboard/index.html` — root tokens, landing, dashboard, cards, panels, and motion styles.
- Test: browser at `http://127.0.0.1:8712`.

**Interfaces:**
- Consumes: existing classes `.landing`, `.landing.hide`, `.dashboard`, `.card`, `.panel`, and `enterDashboard()`.
- Produces: unchanged DOM IDs and a visually clearer light path hierarchy for Task 2.

- [ ] **Step 1: Establish a static shell check**

Run: `python -m py_compile server.py collectors.py`

Expected: exits with code 0; frontend-only work does not introduce a backend dependency.

- [ ] **Step 2: Update CSS visual tokens and surface hierarchy**

In the `<style>` block, retain the existing token names and make path contrast and surfaces use the approved palette:

```css
:root {
  --bg: #f8fafc;
  --card: rgba(255,255,255,.86);
  --border: rgba(148,163,184,.32);
  --text: #0f172a;
  --dim: #64748b;
  --accent: #0d9488;
}
.panel, .card { backdrop-filter: blur(12px); }
```

Keep text, data-card, chart, and table selectors intact so existing render code continues to target the same DOM.

- [ ] **Step 3: Implement the explicit landing-to-dashboard transition**

Style `.landing.hide` to fade, blur slightly, and disable pointer events. Apply `.dashboard.ready` only after the click transition begins so the dashboard starts at full opacity without blocking the loading API request.

```js
function enterDashboard() {
  $('landing').classList.add('hide');
  $('dashboard').classList.add('ready');
}
```

- [ ] **Step 4: Verify interaction and reduced motion**

Start `python server.py`, open the page, activate the Start button using Enter, and reload with reduced motion emulated. Expected: the dashboard appears, focus remains visible, and the page is static when reduced motion is active.

### Task 2: Make the Background Paths effect controlled and non-distracting

**Files:**
- Modify: `projects/token-dashboard/index.html` — `buildPaths()` and path-motion CSS.
- Test: browser at desktop and 560px widths.

**Interfaces:**
- Consumes: `buildPaths(host, opts)` calls for `landingPaths` and `bgPaths`.
- Produces: the same generated SVG structure with stable animation timing and usable `prefers-reduced-motion` fallback.

- [ ] **Step 1: Add deterministic motion settings**

Replace random duration and delay values in `buildPaths()` with index-derived values, preserving the supplied `count`, `color`, and `width` options:

```js
const duration = 22 + (i % 7) * 1.4;
p.style.animationDuration = `${duration}s, ${7 + (i % 4)}s`;
p.style.animationDelay = `${-(i * 1.7)}s, ${-(i % 5)}s`;
```

- [ ] **Step 2: Separate landing and dashboard opacity**

Pass a new `opacity` option from each call site and apply it directly to paths. Use higher opacity for `landingPaths` and lower opacity for `bgPaths` so dashboard text and charts remain the visual priority.

```js
p.style.opacity = String(opts.opacity ?? 0.35);
buildPaths($('landingPaths'), { count: 36, color: '#475569', width: 1, opacity: 0.42 });
buildPaths($('bgPaths'), { count: 24, color: '#cbd5e1', width: .8, opacity: 0.18 });
```

- [ ] **Step 3: Complete the reduced-motion rule**

Add a rule that stops `.bg-paths path` animation under `prefers-reduced-motion: reduce`; do not hide the paths, because their static composition remains part of the visual design.

```css
@media (prefers-reduced-motion: reduce) {
  .bg-paths path { animation: none; }
}
```

- [ ] **Step 4: Verify path quality**

Inspect at desktop and 560px widths for clipped controls, flickering, visible path dots, and horizontal page overflow. Expected: only smooth continuous lines are visible, and all dashboard content remains interactive.

### Task 3: Run end-to-end regression checks

**Files:**
- Modify: none.
- Test: `projects/token-dashboard/server.py`, `/api/data`, and the browser dashboard.

**Interfaces:**
- Consumes: unchanged API responses and the existing `tick()` → `render(d)` path.
- Produces: evidence that the visual change has not altered token-data behavior.

- [ ] **Step 1: Validate Python sources**

Run: `python -m py_compile server.py collectors.py`

Expected: exits with code 0.

- [ ] **Step 2: Validate API output**

Run: `python server.py --port 8712` in a background process, then `Invoke-RestMethod http://127.0.0.1:8712/api/data | ConvertTo-Json -Depth 3`.

Expected: response contains `stats`, `sources`, `hourly`, `daily`, `model_rank`, `agent_summary`, and `recent`.

- [ ] **Step 3: Validate browser rendering**

Load the root page, click Start, wait for one refresh cycle, and inspect the four chart regions plus the recent-records table. Expected: all regions render without console errors and continue to refresh.

- [ ] **Step 4: Record completion evidence**

Use the Workspace `finish` command with the changed `index.html` path, the Python compilation result, API result, and visual verification summary.
