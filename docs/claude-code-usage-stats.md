# How usage & stats data flows in Claude Code

Quick reference for where tools (statuslines, usage meters, cmdvault) can get
runtime stats from — and where they can't.

## The three sources

```
                       ┌──────────────────────────────┐
                       │         Claude Code          │
                       └──────┬──────────┬────────────┘
                              │          │
              JSON on stdin,  │          │  JSON on stdin,
              every refresh   │          │  every event
                              ▼          ▼
                      ┌────────────┐  ┌────────────┐     ┌──────────────────┐
                      │ statusline │  │   hooks    │────▶│ transcript JSONL │
                      │   script   │  │ (PostTool… │     │ (via transcript_ │
                      └────────────┘  │  Stop, …)  │     │  path field)     │
                                      └────────────┘     └──────────────────┘
```

### 1. Statusline — the live gauge

The one place with **rate-limit (usage-limit) data**. Claude Code pipes JSON to
your statusline command; interesting fields:

| Field | What it is |
|---|---|
| `rate_limits.five_hour.used_percentage` / `.resets_at` | 5-hour window usage (Pro/Max only) |
| `rate_limits.seven_day.used_percentage` / `.resets_at` | weekly limit (Pro/Max only) |
| `cost.total_cost_usd` | session cost estimate |
| `context_window.used_percentage` | how full the context is |
| `context_window.current_usage.*` | input/output/cache token breakdown |

Caveats: `rate_limits` appears only for Claude.ai Pro/Max subscribers (not API
key users), and only after the first response. A user runs exactly **one**
statusline script, so a tool that wants a slot there has to share the line.

### 2. Hooks — events, but no money

Hook payloads (PreToolUse, PostToolUse, Stop, SessionEnd, …) carry **no cost,
token, or limit data at all** — just session id, cwd, tool name/input/response,
and `transcript_path`. This is why cmdvault's capture hook can't see usage.

### 3. Transcript JSONL — the raw history

Every hook payload includes `transcript_path`. That file has the full message
history *including per-response token counts*. No rate-limit info, but you can
reconstruct spend per session/model/day yourself. This is what usage-dashboard
tools (ccusage, moshi-style meters) actually parse.

## Rule of thumb

- Want **"how much do I have left?"** → statusline JSON (Pro/Max only).
- Want **"how much did I use?"** → parse transcripts from any hook.
- Want it from a hook directly → you can't; grab `transcript_path` instead.
- `/usage` shows all of it interactively but isn't scriptable.

*(Checked against docs at code.claude.com, July 2026.)*
