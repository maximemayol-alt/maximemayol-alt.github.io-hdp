# CLAUDE.md — Basketball HDP Calculator

## Project Overview

Single-page web application (SPA) for basketball handicap (HDP) betting line analysis. The tool performs statistical modeling, Monte Carlo simulations, and expected value (EV) calculations to evaluate basketball betting lines.

**Language:** French (UI text, comments, and documentation)
**Tech Stack:** Vanilla HTML5 + CSS3 + JavaScript — no framework, no build system
**Deployment:** GitHub Pages (static hosting, single file)

---

## Repository Structure

```
/
├── index.html      # Entire application (HTML + CSS + JS, ~1073 lines)
├── README.md       # Minimal description
└── CLAUDE.md       # This file
```

Everything lives in `index.html`. There is no build step, no bundler, no package.json.

---

## Development Workflow

### Running the App
- Open `index.html` directly in a browser — no server needed
- Or serve with any static file server: `python3 -m http.server 8080`

### Making Changes
1. Edit `index.html` directly
2. Refresh the browser to test
3. Commit and push — GitHub Pages deploys automatically

### Git Branch Convention
- Feature branches: `claude/<description>-<session-id>`
- Push: `git push -u origin <branch-name>`

---

## Architecture

### Single-File Structure (index.html)

| Section | Description |
|---|---|
| `<style>` | All CSS — dark theme with CSS custom properties |
| Auto-import | API-Sports team search and stat fetching UI |
| Paste scores | Manual game result entry |
| Calculation modes | Stable mode, global/contextual toggle, recency weighting |
| Stats input tables | 5-match history for home/away contexts |
| Global stats | Full-season stats for blended mode |
| Manual adjustments | Fine-tune model output |
| Betting lines table | Input market odds, view EV/probability |
| Verdict & best pick | Model recommendations with quality indicators |
| PS3838 parser | Parse betting format data |

### JavaScript Architecture

All code is in global scope — no modules, no classes.

**Function categories:**

| Category | Functions |
|---|---|
| UI Control | `setFav()`, `setStable()`, `setModeGlobal()`, `setRecency()` |
| Calculations | `recalc()`, `normCdf()`, `std()`, `mean()`, weighted mean |
| Rendering | `updateAdjUI()`, `drawHistogram()`, `makeRows()`, `addLineRow()` |
| API Integration | `tsdbFetch()`, `tsdbSearch()`, `loadStats()`, `tsdbGetLast5()` |
| Data Parsing | `parsePs3838Block()`, `parsePasteBlock()`, `readTeam()` |
| Utilities | `formatSigned()`, `randn()`, `erf()` |

---

## Key Business Logic

### Probability Model
- Normal distribution for price probability via `normCdf()`
- Monte Carlo simulation (20,000 samples) for histogram visualization
- Sigma quality metric: 9 = excellent, 15+ = unreliable

### True Line Calculation
```
μ = score_dom - score_ext   (adjusted for pace and ratings)
EV = (Probability × Odds) - 1
Best Pick = highest EV line across all inputs
```

### Pace Adjustment
- `LEAGUE_PACE_BASE = 165.0` PPM (points per minute)
- Normalizes scoring for faster/slower pace teams

### Recency Weighting
When enabled, applies descending weights to the 5 games: `1.0, 0.85, 0.70, 0.55, 0.40`

### User Preferences (localStorage)
| Key | Description |
|---|---|
| `hdp_v5_stable` | Stable mode on/off |
| `hdp_v5_modeGlobal` | Global vs contextual mode |
| `hdp_v5_recency` | Recency weighting on/off |

---

## CSS Conventions

### Color System (CSS Custom Properties)
```css
--bg:    #080C17   /* Dark background */
--card:  #0F1A2E   /* Card background */
--ink:   #E2E8F0   /* Primary text */
--muted: #94A3B8   /* Secondary text */
--blue:  #3B82F6   /* Primary accent */
--green: #00C896   /* Positive/good */
--amber: #FFB800   /* Warning */
--red:   #FF4D4D   /* Bad/error */
```

### Component Classes
| Class | Usage |
|---|---|
| `.card` | Main content containers |
| `.pill` / `.pillbar` | Toggle button groups |
| `.badge` | Status indicators |
| `.verdict` | Output recommendation boxes |
| `.sigma-fill` | Progress/quality indicator |
| `.warn-banner` | Warning messages |
| `.mini` | Small auxiliary text |
| `.label` | Section headers |

---

## API Integration

### API-Sports Basketball (current)
- Endpoint: `v1.basketball.api-sports.io`
- Used for: team search, last 5 games stats, season stats
- Key functions: `tsdbFetch()`, `tsdbSearch()`, `loadStats()`, `tsdbGetLast5()`
- Requires API key entered by the user in the UI
- Falls back to manual paste input if API fails

### Supported Data Formats
- Paste scores: `105 98` or `105-98`
- PS3838 spread/odds format
- API-Sports JSON responses

---

## Coding Conventions

- **Language:** French comments and UI strings
- **Naming:** camelCase for variables and functions
- **State:** Global variables for app state (`favSide`, `stableMode`, `modeGlobalOnly`, etc.)
- **DOM:** `getElementById()` for selection, `insertAdjacentHTML()` for dynamic content
- **Events:** `onclick` attributes in HTML (not `addEventListener`)
- **Visibility:** `classList.toggle()` for show/hide
- **Comments:** Section dividers with `// ──────────────────────────────────────`

---

## Constraints & Limitations

- No modularization — all code in one file
- No debouncing — `recalc()` fires on every input change
- No TypeScript — plain JavaScript
- No tests — manual browser testing only
- Odds validation range: 1.3–3.5 (sports betting context)
- Minimum recommended sample: 3 games (warns below this)

---

## When Editing This Project

1. **Always edit `index.html`** — it is the only source file
2. **Preserve French** in all UI text and comments
3. **Do not add a build system** unless explicitly requested
4. **Keep CSS inline** in the `<style>` block at the top of the file
5. **Keep JS inline** before `</body>`
6. **Test locally** by opening the file in a browser before committing
7. **Do not introduce external dependencies** (no npm, no CDN imports) unless explicitly requested
