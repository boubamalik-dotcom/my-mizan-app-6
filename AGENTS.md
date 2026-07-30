# AGENTS.md

## Cursor Cloud specific instructions

This is a single-page Create React App frontend (React 18 + `react-scripts` 5). There is no backend; Tailwind is loaded via CDN in `public/index.html`, so there is no Tailwind build step or config file. Icons come from `lucide-react`.

Standard commands (see `package.json`):
- Dev server: `npm start` (webpack-dev-server on port 3000; set `BROWSER=none` in headless environments). Supports hot reload.
- Build: `npm run build` (outputs to `build/`).
- Lint: there is no dedicated lint script; lint runs as part of `npm start`/`npm run build` via the CRA `react-app` ESLint config. To lint standalone: `npx eslint src --ext .js,.jsx`.
- Tests: `npm test` (or `CI=true npx react-scripts test`). The repo currently ships no test files, so a bare `npm test` reports "No tests found" and exits non-zero; add `--passWithNoTests` if you need a zero exit.

Non-obvious notes:
- `src/index.js` imports `./App`, which resolves to `src/App.jsx` (CRA resolves the `.jsx` extension automatically).
- Core flow: dashboard → tap "صوّر إجابتك الآن" → scanner screen animates the 5 layers to 100% → auto-transitions to the results screen (with feedback tabs). The scanner progress `useEffect` in `src/App.jsx` caps progress at 100 and schedules the transition once it reaches 100.
