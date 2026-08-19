# Open-source and data attribution

This inventory was checked on 2026-08-19 against `backend/pyproject.toml`,
`backend/uv.lock`, `dashboard/package.json`, `dashboard/package-lock.json`, installed
Python distribution metadata, and installed npm package metadata. It covers direct
declared dependencies; each lock file also contains transitive packages whose notices
must remain available in a distributed build.

## Runtime data and maps

- **King County Freshwater Swim Beach Data** (`mbzm-4r9y`) — seasonal swim-beach
  environmental observations. The official page labels the dataset “Public Domain U.S.
  Government”: https://data.kingcounty.gov/Environment-Waste-Management/Freshwater-Swim-Beach-Data/mbzm-4r9y
- **King County Water Quality Monitoring Dashboard - Monitoring Sites** (`e9bt-i75a`)
  — monitoring-site names and coordinates joined by reviewed locator. The official page
  does not display a license name in the captured metadata, so do not infer one; verify
  its current terms before submission:
  https://data.kingcounty.gov/dataset/Water-Quality-Monitoring-Dashboard-Monitoring-Site/e9bt-i75a
- **King County GIS `WTRBDY_AREA_485`** — official polygon geometry used for the three
  reviewed shoreline fixtures. The service identifies King County as the source; verify
  the linked King County GIS terms for the final distribution:
  https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/WTRBDY_AREA_485/FeatureServer/0
- **OpenStreetMap contributors** — dashboard tiles and Nominatim-based onboarding lookup.
  OpenStreetMap data is licensed under ODbL and requires visible contributor attribution:
  https://www.openstreetmap.org/copyright

These inputs are not emergency-event records. The swim-beach and monitoring-site rows
are access/environmental proxies, and the committed shoreline files are reviewed local
geometry snapshots with their source query URLs retained in `backend/fixtures`.

## Backend direct dependencies

Versions and license labels below come from installed `.dist-info` metadata or bundled
license files in `backend/.venv`.

| Package | Installed version | License metadata |
|---|---:|---|
| FastAPI | 0.139.0 | MIT |
| Uvicorn | 0.51.0 | BSD-3-Clause |
| websockets | 15.0.1 | BSD-3-Clause |
| Ultralytics | 8.4.90 | AGPL-3.0 |
| Shapely | 2.1.2 | BSD-3-Clause |
| GeoPandas | 1.1.4 | BSD-3-Clause |
| sodapy | 2.2.0 | MIT |
| NumPy | 2.5.1 | BSD-3-Clause plus bundled 0BSD, MIT, Zlib, and CC0-1.0 components |
| SciPy | 1.18.0 | BSD-3-Clause core; bundled third-party notices also apply |
| Pydantic | 2.13.4 | MIT |
| HTTPX | 0.28.1 | BSD-3-Clause |
| PyJWT | 2.13.0 | MIT |
| cryptography | 49.0.0 | Apache-2.0 OR BSD-3-Clause |
| Supabase Python client | 2.31.0 | MIT |
| pytest | 9.1.1 | MIT |

`sodapy` remains required: the reviewed King County connector uses a Socrata client.
Removing the obsolete generic fallback did not remove that reviewed network path.

**Ultralytics requires a deployment decision, not just an attribution line.** The
installed package says AGPL-3.0. Ultralytics' official licensing page states that other
distributions or proprietary/embedded deployments may require an Enterprise license:
https://www.ultralytics.com/license. Before distributing code, weights, a hosted service,
or hardware, confirm the exact package, model/weights, source-release obligations, and
deployment terms. Do not assume a classroom/demo use automatically resolves every
distribution obligation.

## Frontend direct dependencies

Versions and license labels come from the installed packages in
`dashboard/node_modules`.

| Package | Installed version | License metadata |
|---|---:|---|
| `@gsap/react` | 2.1.2 | See GSAP Standard License |
| `@supabase/supabase-js` | 2.110.1 | MIT |
| `gsap` | 3.15.0 | GSAP Standard “no charge” License |
| `leaflet` | 1.9.4 | BSD-2-Clause |
| `lucide-react` | 0.468.0 | ISC |
| `react` | 18.3.1 | MIT |
| `react-dom` | 18.3.1 | MIT |
| `react-router-dom` | 7.18.1 | MIT |
| `@testing-library/jest-dom` | 6.9.1 | MIT |
| `@testing-library/react` | 16.3.2 | MIT |
| `@types/leaflet` | 1.9.21 | MIT |
| `@types/react` | 18.3.31 | MIT |
| `@types/react-dom` | 18.3.7 | MIT |
| `@vitejs/plugin-react` | 4.7.0 | MIT |
| `jsdom` | 29.1.1 | MIT |
| TypeScript | 5.9.3 | Apache-2.0 |
| Vite | 5.4.21 | MIT |
| Vitest | 2.1.9 | MIT |

GSAP is **not MIT-licensed**. Both installed `gsap` and `@gsap/react` point to the
official GSAP Standard License: https://gsap.com/standard-license/. Confirm the final
site's use and distribution remain within those current terms.

## Pre-submission license verification checklist

- [ ] Re-run dependency installation from both lock files and regenerate this version
      inventory if resolution changes.
- [ ] Export or retain notices for all transitive Python and npm packages, not only the
      direct table above.
- [ ] Confirm current King County terms for `e9bt-i75a` and `WTRBDY_AREA_485`; do not
      guess a license that the official metadata does not name.
- [ ] Keep “© OpenStreetMap contributors” visible on every map and link to ODbL terms.
- [ ] Confirm tile and Nominatim usage policies for the final hosted traffic level.
- [ ] Review the current GSAP Standard License for the submitted/hosted use.
- [ ] Decide whether Ultralytics code and the exact model/weights will be distributed or
      deployed; satisfy AGPL-3.0 or obtain applicable permission before doing so.
- [ ] Verify icons, screenshots, video music, fonts, training data, and any later-added
      assets separately; they are not covered by the software tables.
- [ ] Include the final notices and source links with the submitted repository/build.
