# Local browser verification

For a new audit without overwriting prior evidence, set `ATLAS_BROWSER_EVIDENCE_SUBDIR=gate-1/browser` before running. Output stays inside `docs/implementation/evidence/`. The default remains `browser` for the original Phase 3A workflow. Gate 1 uses the built preview on port 4173.

Start Django on `127.0.0.1:8000` and Vite on `127.0.0.1:5173`. Use the supported Node runtime and run `npm run test:browser` in `frontend/`. The pinned Playwright package is installed by `npm ci --ignore-scripts`; the default uses an existing Google Chrome installation.

For another executable set `ATLAS_BROWSER_EXECUTABLE` to its path. For installed Playwright Chromium, set `ATLAS_BROWSER_CHANNEL=chromium`; its free browser install is a separate `npx playwright install chromium` command. To verify the built preview after `npm run build` / `npm run preview`, set `ATLAS_FRONTEND_URL=http://127.0.0.1:4173`.

The script accepts only a local frontend, blocks external browser requests and invokes the real Django sample API. Complete, partial and No Travel analyses are real backend calculations. The quota/loading error uses an explicitly injected test HTTP response; constructor WebGL failure is simulated. Those checks do not prove provider behavior or physical GPU performance.

PNG previews and structured pass/fail/timing results are written to `docs/implementation/evidence/browser/`. It exits nonzero on any failed assertion. Screens use 1440×900 and 390×844 viewports. Mobile has a bounded content scroller above its navigation; forecast/inspector captures show different scroll positions at the same viewport. The script uses reduced motion, native dialog keyboard interaction and SwiftShader software rendering. Full screen-reader, Safari/Firefox, physical mobile and hardware GPU validation remain open.
