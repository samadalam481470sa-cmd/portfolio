# Portfolio

Projects by Samad Alam, UT Dallas, B.S. Information Technology Systems, graduating December 2026.

## Projects

| Project | What it does | Stack | Code |
| --- | --- | --- | --- |
| Newport Acquisition CRM | Enterprise M&A / acquisition deal-management app for Newport Specialty Partners. | React 19, TypeScript, Vite, Tailwind CSS, Express, SQLite | [newport-acquisition-crm](newport-acquisition-crm/) |
| HomeGrok | HomeGrok fully runs an AI trainer on your own GPU — you can teach it anything. | Python, PyTorch | [homegrok](homegrok/) |
| Market Agent Connector | Connects Polymarket, Kalshi, and Robinhood through their APIs, with an AI trading engine and paper-trading sandbox. | Python, FastAPI, MCP | [market-agent-connector](market-agent-connector/) |
| Job Finder | Scheduled discovery and resume matching against public job APIs. A self-hosted multi-user web UI is in `newport-acquisition-crm/web`. | Node.js | [job-finder](job-finder/) |
| Resume-Fit Autofill Assistant | Chrome extension that fills application fields from a resume you provide and scores keyword overlap with the posting. | JavaScript, Manifest V3 | [job-application-chrome-extension](job-application-chrome-extension/) |
| Stock news sentiment | Turns news into per-ticker sentiment signals. Research tool, not trading advice. | Python, SQLite, pandas, VADER, optional FinBERT | [stock-sentiment](stock-sentiment/) |
| Wholesale Hub | Finds products that sell for more on a marketplace than they cost at a wholesale store, and shows the links and buying steps. | Python, FastAPI, SQLite | [wholesale-hub](wholesale-hub/) |
| EstateIQ | Collects listings, market indicators, and migration/growth signals, then scores properties for investment focus. | Python, SQLite, HTML/CSS/JS | [estateiq](estateiq/) |
| Curb Connect | Contractor/subcontractor project tracker for curb and site concrete work. | React 19, TypeScript, Vite | [curb-connect](curb-connect/) |
| NEXUS Chain | Live public-testnet crypto ledger with native token **NXN** (wallets, transfers, blocks, faucet, explorer) + enterprise modules. | Go, Cosmos-style modules, Docker | [nexus-chain](nexus-chain/) |

HomeGrok fully runs an AI trainer on your own GPU — you can teach it anything.

*(Uses Apple Metal or NVIDIA CUDA when available; falls back to CPU otherwise.)*

Each folder has its own README with how to run that project.

## Tech stack

- **TypeScript / React:** Newport Acquisition CRM (Vite, Tailwind CSS, React Router, Recharts, Zod, Express, `better-sqlite3`). Curb Connect (Vite, browser local storage).
- **Browser:** Resume-Fit Autofill Assistant, Manifest V3, no framework.
- **Node.js:** Job Finder and its multi-user web service use the Node standard library only. The CRM API uses Express.
- **Python:** HomeGrok (PyTorch, NumPy, plus PDF/Word readers and Playwright for the application filler), Market Agent Connector (FastAPI, MCP, httpx, Pydantic), stock news sentiment (SQLite, pandas, VADER, optional FinBERT and Streamlit), Wholesale Hub (FastAPI, SQLite), EstateIQ (SQLite, standard library only, plus a static website).
- **Go / blockchain:** NEXUS Chain (Cosmos SDK + CometBFT–oriented L1 scaffold, custom financial modules, gateway, indexer SQL, connector stubs).

## About

Samad Alam is completing a B.S. in Information Technology Systems at the University of Texas at Dallas, graduating December 2026. This repository collects the projects above.

GitHub: [samadalam481470sa-cmd](https://github.com/samadalam481470sa-cmd)
