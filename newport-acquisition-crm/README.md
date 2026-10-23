# Newport Specialty Partners — Acquisition CRM

Enterprise M&A / acquisition deal-management app for Newport Specialty Partners.

> This folder is the Newport Acquisition CRM. The multi-user job-finder service that shipped beside it is in `web/` (it reads `../../job-finder`). Other portfolio projects are sibling folders; see the repository README.

## Stack

- React 19 + TypeScript + Vite + Tailwind CSS
- Express API + SQLite (`better-sqlite3`) database
- Lucide icons, Recharts, Zod validation
- Helmet, rate limiting, hashed sessions & API keys, audit logging + permanent change history

## Run locally

```bash
npm install
npm run dev
```

- Web: http://localhost:5173
- API: http://localhost:3001

## Sign in

1. **Sign in — Demo access** enters the dashboard (Dennis session).
2. Or authenticate with the local demo API key (slot 1 only):
   `nwp_demo_key_slot1_replace_me_by_security_team`

Production will use **five API key slots** provisioned by the security team. This app stores **hashes only**.

## 24/7 static demo (GitHub Pages)

`npm run build` with `STATIC_DEMO=1` writes a static demo. The portfolio workflow `.github/workflows/deploy-pages.yml` runs that build from this folder.

An earlier copy was published at https://samadalam481470sa-cmd.github.io/sammyyyy/

On static hosting, edits persist in the browser (`localStorage`) so reopening the link keeps your changes.

## Modules

Dashboard, Opportunities, Projects, Relationships, Tasks, Sources/Bankers, Carriers/Reinsurers, Portfolio, Documents, Reports, Security.

## Related projects

These live next to this folder in the portfolio:

- **Newport Acquisition CRM** (this folder) — Enterprise M&A / acquisition deal-management app for Newport Specialty Partners.
- **[homegrok](../homegrok/)** — Local AI assistant and job-application helper that runs on your machine (Python).
- **[market-agent-connector](../market-agent-connector/)** — Python AI agent connector for Kalshi and Polymarket prediction markets and stock trading via MCP and REST.

## HomeGrok

HomeGrok fully runs an AI trainer on your own GPU — you can teach it anything.

<small><em>(Uses Apple Metal or NVIDIA CUDA when available; falls back to CPU otherwise.)</em></small>

The trainer (`./hg learn`, `train`, `evolve`, and `pipeline` in [`../homegrok/`](../homegrok/)) uses a GPU when Apple Metal or CUDA is available, and otherwise trains on the CPU.
