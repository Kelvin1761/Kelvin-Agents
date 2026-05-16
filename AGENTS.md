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
- **HKJC Mainline**: `HKJC Wong Choi` 已升級為 full Python pipeline；主入口係 `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py`
- **HKJC Legacy**: 舊版入口暫時保留於 `.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator_legacy.py`，只供過渡或比對
- **AU Mainline**: `AU Wong Choi` 已升級為 full Python pipeline；主入口係 `.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py`
- **AU Legacy**: 舊版入口暫時保留於 `.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator_legacy.py`，只供過渡或比對
- **Cross-Platform**: All scripts support macOS + Windows. macOS/Linux 可用 `python3`，Windows 通常用 `python`。Windows users must set `PYTHONUTF8=1` env variable.
