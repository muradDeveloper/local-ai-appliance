# Handoff — Implementation Plan Tooling (2026-07-26)

## Context

Working repository: `C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance`

The project is a private GPU-accelerated AI appliance (Proxmox Ubuntu VM, RTX 3060, Docker Compose). No code has been deployed yet — the VM has not been provisioned. This session focused entirely on the planning and tooling layer, not on the stack itself.

Primary planning documents:
- `docs/IMPLEMENTATION-PLAN.md` — authoritative source of truth (Markdown)
- `docs/IMPLEMENTATION-PLAN.html` — interactive tracker derived from the MD

---

## What Was Done This Session

### 1. `scripts/generate-secrets.sh`
Added `MEM0_DB_PASSWORD` generation line alongside the other DB passwords.

### 2. `docs/IMPLEMENTATION-PLAN.md`
Added **Phase −1 — Proxmox VM provisioning** as the new first phase, before Phase 0. It covers:
- IOMMU setup on Proxmox host
- VM creation (minimum specs: 8 vCPU `host` type, 32 GB RAM, 32 GB OS disk, 200 GB data disk at `/var/lib/docker`, RTX 3060 full PCIe passthrough)
- Ubuntu Server 24.04 LTS install with static IP `192.168.1.63`
- NVIDIA driver 570, Docker Engine, NVIDIA Container Toolkit
- GPU passthrough verification
- Repository clone

Also updated the Pre-conditions section (VM provisioning is now a phase, not a pre-condition).

### 3. `scripts/sync-plan-html.js` (new file)
Node.js script that reads `docs/IMPLEMENTATION-PLAN.md` and rewrites the `PHASES` and `OPEN_ITEMS` arrays in `docs/IMPLEMENTATION-PLAN.html`. Run with:
```bash
node scripts/sync-plan-html.js
```
Parses per phase:
- `goal` — text after `**Goal:**`
- `details` — content between goal and first task (tables, file lists, notes) → rendered as HTML
- `tasks[].body` — content between consecutive task headers (commands, code blocks) → rendered as HTML

Key bugs fixed during development:
- Phase −1 task IDs use Unicode minus `−` (U+2212); regex updated to `[-−\d]+`
- Phase label regex in HTML render functions updated to `/Phase [-−]?\d+ — /`

### 4. `docs/IMPLEMENTATION-PLAN.html`
Significant UI changes:
- **Accordion tasks** — each task row is now an accordion. Header = task text (checkbox + ID + description); panel = the commands/body from the MD. Checkbox click marks done (independent of accordion toggle).
- **Accordion phase goal** — the goal text is the accordion header; the panel shows details (resource tables, Files sections, etc.) from the MD.
- **Copy-paste fixed** — `user-select: none` removed from task rows; text in panels is selectable.
- **Panel content styles** — tables, `<pre>` code blocks, blockquotes, lists all styled within panels.
- `toggle()` updated to use `data-key` attribute instead of matching `onclick` string.
- `expandTask()` and `expandGoal()` functions added.

### 5. `C:\Users\murad.karrar\.claude\rules\security-gates.md`
Clarified that `.scratch/` always refers to the **project workspace root** `.scratch/`, never `AppData\Local\Temp` or any system temp path.

---

## Current State

| Area | Status |
|---|---|
| `sync-plan-html.js` | Working — 9 phases, 10 open items, task bodies, phase details |
| HTML accordion UI | Working — expand/collapse, checkbox toggle, copy-paste |
| Phase −1 in MD + HTML | Complete |
| Open items 3, 7, 8 | Fixed (`MEM0_DB_PASSWORD`, Phase −1 added) |
| VM provisioned | No — Phase −1 not yet executed |
| Any Docker services running | No |

---

## What Is NOT Done (Next Steps)

The implementation plan itself has not been executed. The next session should begin at **Phase 0** on the actual VM:

1. `mv compose/.env .env` (open item 10)
2. Add missing `.env.example` placeholders (open item 8)
3. Pin `:latest` image tags for faster-whisper, Kokoro, Mem0 (open item 6)
4. Run `./scripts/generate-secrets.sh` and `./scripts/preflight.sh`
5. Then proceed through Phases 1–7 per `docs/IMPLEMENTATION-PLAN.md`

Alternatively, if continuing plan tooling work, the HTML still has these gaps:
- **Global Constraints** section from the MD has no HTML representation (deferred by design)
- Pre-conditions card in the HTML is hardcoded — if the MD pre-conditions change, the HTML card must be manually updated

---

## Key File Paths

| File | Purpose |
|---|---|
| `docs/IMPLEMENTATION-PLAN.md` | Source of truth — edit this, then run sync |
| `docs/IMPLEMENTATION-PLAN.html` | Interactive tracker — generated from MD |
| `scripts/sync-plan-html.js` | MD → HTML sync script |
| `scripts/generate-secrets.sh` | Secret generation (generates `.env` from `.env.example`) |
| `scripts/preflight.sh` | Pre-deployment validation script |
| `docs/ARCHITECTURE.md` | Stack architecture reference |
| `docs/DECISIONS.md` | Open architectural decisions |
| `.env.example` | Placeholder env file (committed) |
| `.env` | Real secrets (gitignored, not yet generated on VM) |

---

## Suggested Skills

- **`/execute`** — when starting to implement a phase on the VM (runs `superpowers:executing-plans` style)
- **`/chrome-devtools-mcp`** — for verifying HTML plan changes in the browser before committing
- **`/run`** — if a dev server or Docker service needs to be started and verified
- **`/review`** — before any Compose or shell script changes go to the VM
- **`/commit`** — changes in this session were never committed; the sync script, HTML accordion changes, and generate-secrets.sh change should be committed first

---

## Gotchas

- The HTML file is **generated** by `sync-plan-html.js` — do not hand-edit the `PHASES` or `OPEN_ITEMS` JS arrays directly. Edit the MD and re-run the sync script.
- Phase −1 task IDs use Unicode minus `−1.1` not ASCII `-1.1`. This is in the MD and handled by the sync script.
- `AUTHENTIK_LISTEN__HTTP: 0.0.0.0:9000` must remain in the Authentik service env — Authentik 2026.5.x changed its default listen address to IPv6 `[::]` which breaks on IPv6-disabled hosts.
- The `.env` file does not exist yet — it needs to be created on the VM by running `generate-secrets.sh`.
- Disk cache setting for Proxmox VM disks: use **None** (avoids double-caching with ZFS ARC).
- Ubuntu Server 24.04 LTS is the chosen OS (not Debian) — NVIDIA driver tooling is simpler.
