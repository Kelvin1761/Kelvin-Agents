<!-- This file provides cross-platform agent compatibility (Claude Code, Gemini CLI, Cursor). -->
<!-- The canonical rules are in .agents/rules/GEMINI.md -->

# Antigravity Agent Instructions

> **Primary ruleset:** See [`.agents/rules/GEMINI.md`](.agents/rules/GEMINI.md) for the full agent protocol.
> **Architecture:** See [`.agents/ARCHITECTURE.md`](.agents/ARCHITECTURE.md) for system map.
> **Setup Guide:** See [`SETUP.md`](SETUP.md) for installation and cross-platform configuration.

## Quick Context

- **Project**: Antigravity — AI-powered prediction & analysis kit (HKJC Racing, AU Racing, NBA, LoL Esports)
- **Language**: Hong Kong Chinese (繁體中文) for responses and implementation plans, English for code
- **Agents**: 22 specialists in `.agents/agents/`
- **Skills**: 46 skills in `.agents/skills/`
- **Safe Write**: Use `safe_file_writer.py` instead of direct file writes (Google Drive sync protection)
- **Cross-Platform**: All scripts support macOS + Windows. Use `python` command (not `python3`). Windows users must set `PYTHONUTF8=1` env variable.

