# CLAUDE.md: Summit Ops MCP server (Project 3)

Context for Claude Code. Read README.md for the overview.

## What this is
Portfolio project 3 for Saadat Baig (freelance Agentic Systems Engineer). An MCP server that lets a contractor's owner talk to their business data in Claude, with every write going through server-side rules, a preview/confirm step and an audit log. Fictional company: Summit Heating & Air (a customer of "Fieldwise", the shared fictional SaaS in this portfolio).

Signature principle: **Claude asks. The server decides what's allowed. The audit log records everything.** Rules never live in prompts.

## Current state (handed over from planning)
- Rules, ops layer, MCP server, memory store, seed data and 81 tests are written and passing.
- Seed has exactly one deliberate overlap: trap `mike_thursday_overlap` (Mike, Thu 13:00-14:30) against `mike_thursday_busy` (14:00-16:00). The filler never creates others; `tests/test_seed.py` enforces this.
- Server smoke-tested over stdio with the MCP Python SDK **v2.3.0** (pinned in requirements.txt; `from mcp.server.mcpserver import MCPServer`; v1's FastMCP was renamed). Do not "fix" imports back to FastMCP.
- Evals run against the real Claude API (claude-sonnet-5-5), twice on 2026-10-09: 20/20 passed, 0 unsafe writes both times ($0.4525 and $0.4633 at $2/M input, $10/M output). The second run used the current seed.
- Airtable store and setup/seed scripts run against a real base. `scripts/live_check_airtable.py` passes 36/36 (read results match the memory store; reschedule, refusal, expired/unknown confirm). Fixes made: base ID format in .env, ID tie-break sorting in ops.py (Airtable returns records in no fixed order), confirm_action looks up the preview with a filter formula instead of reading the whole Audit Log.

## Next steps, in order
1. Create `.venv`, `pip install -r requirements.txt`, `python -m pytest -q`. Expect 81 passed.
2. Connect to Claude Desktop via `run_server.py` (see `claude_desktop_config.example.json`). Try the demo prompts in README.
3. Run `python evals/run_evals.py` with an API key. Fix prompt/tool-description issues, never by loosening rules. Record pass rate, unsafe writes, tokens and time per case.
4. Airtable: `scripts/setup_airtable.py` + `scripts/seed_airtable.py` on an empty base, then `STORE=airtable` and re-test. Likely fixes: field type mismatches, Airtable omitting empty fields, rate limits (5 req/s).
5. Demo prep: run the same "50% off" request against Airtable's official MCP for the side-by-side. Show only what actually happens.

## Conventions
- `rules.py` stays pure (no I/O). Every new write tool = a `check_*` rule + `propose_*` + handling in `Ops._recheck`.
- No delete tools. No free-text customer messages.
- Every tool call writes an audit row.
- Tests run offline. Keep them passing before every commit.
- Windows-friendly code (the owner develops on Windows): no `%-I` strftime, use pathlib.
- Don't invent numbers for posts or README. Report only what runs produce.

## Out of scope for v1 (keep for v2)
Twilio sending, per-role permissions, remote hosting (streamable HTTP), Airtable linked records, undo.
