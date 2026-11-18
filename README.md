# GJ Investment Academy · Algo Trading Demo

A local Phase 1 Flask demonstration for exploring simulated strategies, orders, positions, and portfolio analytics. **Everything is simulated:** prices are deterministic examples, historical trades are seeded, risk labels and subscription prices are illustrative, and there is no live broker, payment, or real authentication integration. Do not enter actual credentials.

## Run locally

Requires Python 3.9 or newer and an internet connection for the chart libraries and optional web fonts.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Demo login: **student@gjacademy.com** / **Demo@123**. The Flask secret is ephemeral by default, so restarting the server signs the user out; optionally set `GJ_DEMO_SECRET` for a stable local session. This login is deliberately not production security. Run only on a trusted local machine.

## GitHub Pages

GitHub Pages is static hosting and cannot run Flask. Run `python build_pages.py` to render the existing templates into the root `index.html` and static page routes used by https://gjgenie.github.io/DashboardGJ/. The generated demo login is client-side only; the app remains a simulation and must not be used for real authentication or trading. Re-run the exporter after changing templates or the frontend JavaScript, then commit the generated pages.

## Explore

Sign in to the strategy marketplace, view details, and subscribe using the placeholder credentials `demo-key` and `demo-secret`. They are discarded and never persisted. Activate a subscription to configure risk limits and monitor subscribed strategy activity in the trading terminal. Orders, positions, settings, and analytics share browser-local non-sensitive demo state, which survives refresh. Reset it under Settings. The chart, notification and other Phase 2 placeholders are labeled in the interface. Subscription cancellation or strategy stop never closes an open position. Manual order entry and position closing are not available on this platform. Automated strategy execution is not implemented in Phase 1.

Simulated order quantity is 0.001 BTC, with USD/BTC prices and P&L converted using an illustrative fixed ₹83/USD. Realized P&L equals price difference × BTC quantity × exchange rate, with the sign reversed for shorts. Metrics are derived from closed positions; daily trade and loss limits apply to new entries. The initial balance is ₹100,000 plus realized P&L. Charts and metrics describe demo data only. Chart libraries load from CDNs; if unavailable, tabular data and controls still work. TradingView Lightweight Charts is used with attribution in the terminal, pursuant to its license.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests
node tests/simulation.test.js
```

## Phase 2

Replace demo login with secure identity and authorization; move state and simulation to a durable server-side store; implement audited strategy execution and proper market data; integrate a broker through a secure server-side adapter with credential vaulting and order reconciliation; add payments, registration, notifications, and production-grade security, risk controls, observability, and testing. No broker interface is connected in this phase.
