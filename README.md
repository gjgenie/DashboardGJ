# GJ Investment Academy dashboard

A local Flask demo with simulated strategies, plus an isolated Shark Exchange proof of concept. The simulator and its browser-local data are separate from the Shark account. The local app opens without a sign-in and is **not production security**. Use this local-only app on a trusted macOS user account; do not expose it to a network or use it as a multi-user service.

## Run locally

Python 3.9+, macOS Keychain, and a network connection to Shark are required for the Shark feature.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 to enter the dashboard directly. The Flask secret is ephemeral by default, so restarting rotates the local session. The server binds to loopback. Do not run the development server behind a proxy or on a public interface.

## Local Shark POC

On the local subscription page, enter your Shark API credentials directly in the Shark connection section. A read-only open-orders request must succeed before the credentials are stored in macOS Keychain. The local Shark connection uses IPv4 so Shark sees the public IPv4 address you allowlisted; if your ISP changes that address, update the allowlist. The secret is never redisplayed; disconnect removes the Keychain entry. Do not paste credentials into chat. This is a production exchange account, not a verified sandbox.

The local Dashboard and Trading Terminal include a separate read-only Shark activity section for BTCUSDT futures. It polls open orders, executions, and open positions every 30 seconds while the page is visible, and displays at most 20 recent records per section. Pending orders and executed trades are shown separately; other symbols and older records are outside this POC. Account activity is never added to simulated localStorage.

The terminal has a separate live BTCUSDT order preview. The POC accepts exactly 0.002 BTC, but Shark's current contract metadata, configured margin asset, precision, and the absence of open BTCUSDT orders must also pass verification. An opposite-side order for a verified open position is previewed as reduce-only and tied to that position; same-side increases are blocked. The position is checked again before submission. Position/order checks are snapshots and cannot prevent other clients changing the account concurrently. MARKET previews require a recent Shark ticker estimate; the actual execution price can differ. When an open long is present, SELL is previewed as a reduce-only order for that position; a flat account previews SELL as a new short. The app does not change leverage or margin mode, and order acceptance is not proof of a fill. Verify the outcome on Shark, especially after any network error. An order is never automatically retried.

**Live submission is disabled by default.** Shark's Python example places `deviceType: WEB` and `userCategory: EXTERNAL` in the signed body, although its error list also mentions a device header without naming it. To deliberately test the documented body format after confirming your margin asset, start locally with `SHARK_LIVE_TRADING_ENABLED=1 SHARK_DEVICE_MODE=DOCUMENTED_BODY SHARK_MARGIN_ASSET=USDT python app.py`. The request may be rejected if Shark requires an additional header. Alternatively, after Shark confirms an actual header name and value, use `SHARK_DEVICE_HEADER_NAME` and `SHARK_DEVICE_HEADER_VALUE` instead of the body mode. If metadata or account-state responses cannot be verified, submission fails closed. Review the exact order and account settings before confirming; this uses real funds.

## Static GitHub Pages

The static site is a simulator. The exporter explicitly disables local Shark markup, scripts, tokens, and endpoints. `_config.yml` excludes local app source, templates, tests, and local-only scripts from a standard Jekyll Pages build. This change does not regenerate or publish Pages. Run `python build_pages.py` only when you intend to regenerate the simulator.

## Simulation and tests

Portfolio figures are seeded, and the terminal chart is generated demo data. Simulated P&L uses USD/BTC, BTC quantity, and a fixed illustrative ₹83/USD conversion. These figures do not reflect a Shark account. The chart libraries are bundled for local use; TradingView attribution appears in the terminal.

```bash
.venv/bin/python -m unittest discover -s tests
node tests/simulation.test.js
```

The tests mock exchange and Keychain access; they do not send live requests or place orders. Automated strategy execution, production authentication, payments, and production broker integration remain future work.
