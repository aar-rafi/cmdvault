# Feature proposal: auto-save successful agent commands into Warp Drive

*(draft for github.com/warpdotdev/warp — review before posting)*

**Title:** Auto-capture successful agent-run commands into Warp Drive

---

So here's a thing I kept noticing while using AI agents in the terminal: the agent
writes genuinely good commands — the exact `ffmpeg` incantation, the `git rebase
--onto` I can never remember, the right `jq` filter on the third try — and then
that command just... evaporates. It scrolls away, session ends, gone. Next week I
(or the agent) re-derive it from scratch.

Meanwhile Warp Drive sits right there, but saving to it is manual. Manual curation
is exactly the kind of chore nobody does in the moment, which is why most people's
Drive has like four workflows in it.

**The ask:** when an agent-executed command exits 0, offer to stash it (or just
stash it, behind a setting) into a "Captured" section of Warp Drive.

The part that makes this actually work — and the reason agent commands are *better*
candidates than shell history: **the agent already wrote a natural-language
description of every command before running it.** That description is a perfect
searchable title. Shell history gives you `awk '{print $2}' | sort | uniq -c`;
capture gives you "Count duplicate IPs in access log" with the command attached.
You search by intent, not by trying to remember flag soup.

## What I learned building a prototype

I built this as a plugin for Claude Code (hooks into the tool-call lifecycle,
stores markdown notes, exports to Warp workflow YAML) and a few things turned out
to matter:

1. **Noise filtering is the whole game.** Agents run tons of `ls`, `cat`, `git
   status`. A dumb heuristic gets you ~90% of the way: drop single-token commands
   and a small blocklist of trivial reads; keep anything with pipes/redirects/
   multiline structure, 2+ flags, or 4+ tokens. Without this the library is
   unusable within a day.

2. **Dedupe by normalized command text, count repeats.** The same command
   captured 15 times shouldn't be 15 entries — it should be one entry with a use
   count of 15. The use count is free signal: sort by it and the top of your
   library is automatically your greatest hits.

3. **Store failures somewhere too (just not in the library).** A raw append-only
   log of everything makes a later "smart curation" pass possible — an LLM can
   mine it for gems the heuristics missed. Cheap insurance.

4. **Success detection needs care** — exit code 0 plus "not interrupted by the
   user," since a Ctrl-C'd command is not an endorsement.

Prototype's here if useful as a reference: <repo link>. It exports straight into
`~/.local/share/warp-terminal/workflows/`, so I'm already living with the UX — and
honestly the auto-captured stuff gets reused way more than anything I ever saved
by hand.

## Sketch of the UX

- Setting: `Off / Ask / Auto` (default Ask?) for agent-run commands
- Captured items land in a distinct Drive section, title = agent's description
- Repeat capture bumps a counter instead of duplicating
- Bulk actions: promote to a real workflow (parameterize args), delete, pin

Happy to help spec this properly per the contribution process, and to verify
agent output against my prototype's test cases.
