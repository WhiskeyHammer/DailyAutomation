# Scraper Debug Handoff — 2026-05-12

## Host

Koyeb worker.

| Field | Value |
|---|---|
| App | `few-muskox` (id `2b401c96`) |
| Service | `dailyautomation` (id `dc8b8d38`) — type WORKER |
| Active deployment | `63792d31` — started 2026-05-12 20:22 UTC |
| Region | `was` |
| Status | HEALTHY |
| Domain (other app) | `few-muskox-jeremy-wiggins-fa1efba7.koyeb.app` |

API token is stored at runtime in `$env:KOYEB_TOKEN`. CLI is at `C:\Users\Whisk\bin\koyeb.exe` (v5.10.2). `~/bin` was added to user PATH.

Useful commands:

```powershell
$env:KOYEB_TOKEN = '<token>'
& "$env:USERPROFILE\bin\koyeb.exe" services list
& "$env:USERPROFILE\bin\koyeb.exe" deployments list --service dc8b8d38
# logs require explicit time window (no --tail on closed ranges):
$start = (Get-Date).ToUniversalTime().AddHours(-6).ToString("yyyy-MM-ddTHH:mm:ssZ")
$end   = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
& "$env:USERPROFILE\bin\koyeb.exe" services logs dailyautomation -a few-muskox `
    --type runtime --start-time $start --end-time $end --order desc `
    --regex-search "pipeline|ERROR|TIMED|Sleeping|iteration"
& "$env:USERPROFILE\bin\koyeb.exe" services redeploy dc8b8d38
```

## What I observed in 6h of runtime logs

Loop layout (from [main.py](main.py)): every iteration runs a workout keep-alive (timeout 120s), then SAM hourly, then Junkyard hourly, then sleeps 60–180s.

**Iteration 1 — 20:23 UTC** (only successful Junkyard run in window):
- Junkyard pipeline completed in ~1 min. Ace returned 0 cars (first attempt errored, retry succeeded). GO Pull-It returned 1 car. Email digest sent.
- SAM pipeline started 20:24:56, **TIMED OUT after 900s** at 20:39:56. No retry visible in window.

**Iterations 2–8 — 20:39–20:55 UTC:**
- Workout check throws `Failed to connect to browser` immediately. Underlying error string in the log: *"One of the causes could be when you are running as root. In that case you need to pass no_sandbox=True"*. Despite `--no-sandbox` being on the chromium arg list, nodriver is still rejecting the connection.

**Iterations 9–14 — 20:58–21:36 UTC:**
- Workout check now hangs the full 120s timeout instead of failing fast. Same root cause, different failure mode.

**Last log line: 21:36:42 UTC** — Junkyard pipeline "starting" for iteration 14. No completion line in the window I pulled. Could mean (a) logs trail, (b) Junkyard is still working, (c) it hung — JUNKYARD_TIMEOUT is 600s so if it hung it should have bailed by ~21:46 UTC. Worth re-pulling logs after 22:00 UTC to confirm.

## Root cause hypothesis

The deployment that went live today at 20:22 UTC introduced a chromium/nodriver regression. Three symptoms point at the same bug:

1. Workout check (smallest, simplest browser task) fails 100% of the time after iter 1.
2. SAM scraper hung past its 900s timeout on its only attempt.
3. Junkyard *worked* on iter 1 (cold browser) but iter 14's pipeline hasn't logged completion.

Likely culprits in priority order:

- `browser_config.py` (uncommitted local changes — `git status` shows ` M browser_config.py`). Check `HEADLESS` / `BROWSER_ARGS` against what's deployed. The deployed args include both `--no-sandbox` AND `--disable-setuid-sandbox`, and nodriver still complains it needs `no_sandbox=True` *as a Python argument to `uc.start()`*, not as a chromium CLI flag. See [main.py:50](main.py#L50): `await uc.start(headless=HEADLESS, browser_args=BROWSER_ARGS)` — no `no_sandbox=True` is passed.
- `junkyard_scraper/master_junkyard.py` — uncommitted ` M`. May have introduced a hang on one of the per-yard scrapers, where `nodriver` and chromium drift apart and one yard scrape blocks indefinitely. JUNKYARD_TIMEOUT=600s should catch it but only if `asyncio.wait_for` is wrapping the whole pipeline (verify in [main.py](main.py)).
- The Koyeb instance is `nano`-class memory; chromium OOMs silently. Check instance size in `koyeb services get dc8b8d38 --full -o yaml`.

## Repair plan (in order)

1. **Fix the workout check** — pass `no_sandbox=True` to `uc.start()` in [main.py:50](main.py#L50). This either makes it work or makes the failure mode clean. Same change probably needs to apply to every `uc.start(...)` call across the scrapers (grep first).
2. **Confirm Junkyard iter-14 finished** — pull logs from 21:30 → now. If silent, the run is hung and the timeout isn't wrapping the whole pipeline — fix the wrapping in [main.py](main.py).
3. **Investigate SAM 900s timeout** — pull build-phase and runtime logs for the SAM portion only:
   ```powershell
   & "$env:USERPROFILE\bin\koyeb.exe" services logs dailyautomation -a few-muskox `
       --type runtime --start-time 2026-05-12T20:24:00Z --end-time 2026-05-12T20:40:00Z `
       --regex-search "SAM|sam"
   ```
   Look for "Navigating to" lines that have no follow-up — that's the hang point.
4. **Commit fixes, push, let Koyeb auto-redeploy** (origin is GitHub `WhiskeyHammer/DailyAutomation`, branch `main`, so a push triggers a build). Or run `koyeb services redeploy dc8b8d38` after a manual git push.
5. **Verify** — pull 30 min of logs post-deploy, confirm: workout check completes, SAM runs to completion, junkyard digest email arrives.

## How to let me work unattended

The "approve every PowerShell command" friction is because Claude Code's permission rules for the PowerShell tool don't accept substring wildcards (`PowerShell(*koyeb*)`) the way Bash rules do — only exact-match strings are saved when you click "Allow always". So every new koyeb subcommand prompts again.

Pick whichever fits:

- **For this session (fastest):** press `Shift+Tab` twice to enter **auto-accept edits + tool calls** mode. Then walk away. (Press it again to exit.)
- **For permanent:** run `/permissions` and add an exact-match rule for `PowerShell` that's broad — e.g. allow the `koyeb.exe` invocation form. Or restart Claude Code with `--dangerously-skip-permissions` for this folder only.
- **For belt-and-suspenders:** also persist the API token so I don't have to inline it each time:
  ```powershell
  [Environment]::SetEnvironmentVariable('KOYEB_TOKEN', '<token>', 'User')
  ```

## What I have NOT done yet

- No code changes — only added Koyeb CLI install and one settings.local.json edit.
- No redeploy.
- No verification of the iter-14 outcome (logs cut off at 21:36:42 UTC, before pipeline completion would have logged).
