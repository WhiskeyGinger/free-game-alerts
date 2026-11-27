# Free Game Alerts

Posts free games to a Discord channel: Epic Games' weekly free games (from Epic's own feed) and full-game
giveaways on Steam and GOG (from GamerPower's public feed). Each game is posted once, with its normal price,
when the offer ends (Central time), and a claim link. DLC, loot, betas and free weekends are skipped.

## Setup
1. In Discord: Server Settings → Integrations → Webhooks → New Webhook → pick the channel → Copy Webhook URL.
2. In this repo: Settings → Secrets and variables → Actions → New repository secret
   - Name: `DISCORD_WEBHOOK_URL`, Secret: the webhook URL.
3. Actions → Free game alerts → Run workflow (mode `sample` sends a labelled example; `run` checks for real).

Runs every 2 hours on GitHub's schedule. Posted games are remembered in the workflow cache.

## Files
- `alerts.py` — fetch, filter, de-duplicate, post
- `test_alerts.py` — tests (run with `python -m unittest`)
- `.github/workflows/free-games.yml` — schedule
