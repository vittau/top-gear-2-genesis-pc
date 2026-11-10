# Task 36: unify the Esc menu's video and audio groups

**Status: requested by the owner; coordinate with task 35 in the same worker.**

The owner finds the Esc menu confusing and explicitly requested:

- Display + Graphics + Video become a single **Video** menu.
- Sound + Audio become a single **Audio** menu.

The owner specified the exact category order:

1. **VIDEO**
2. **AUDIO**
3. **SYSTEM**
4. **MODS**
5. **SAVE STATES**

Keep this order in the actual menu and controller focus sequence; do not sort
categories alphabetically or by whichever descriptor is encountered first.
Other non-category commands, if present, keep their established behaviour.

This is an in-game menu organization change. Keep every existing option,
stable setting key, stored value/default, live/restart behaviour and controller
access. Do not reset preferences, duplicate rows, add a replacement menu or
expand the request into a launcher redesign.

Read AGENTS.md and the active task-35 context. Use the existing Sol worker to
avoid concurrent modifications to the filter/runtime UI; commit the grouping
change separately from the filter fix. Only the coordinator triggers CI or
creates a new Deck draft after review. S4 remains unstarted.

Trace both the shared runtime settings descriptors
(`recomp-ui/src/common/recomp_runtime_settings.c`) and host/game additions
(`runner/main.c`, `game/tg2_options.c`, experimental internal-resolution row).
Consolidate all contributing descriptors, not just visible labels. If the
shared runtime requires a new capability, make it reusable/opt-in and place
TG2-specific selection in the game's spec rather than hardcoding the game in
the framework. Follow the project's engine patch discipline; do not leave
unrecorded submodule edits or change an upstream pin to a local-only commit.

Keep rows in a coherent order within the unified categories and maintain
scrolling/focus on Steam Deck-sized output. The exact sub-order can follow
the current ordering where sensible; no new user decision is required.

Verify the actual Esc menu: the five categories in the exact order above,
one Video category, one Audio category, no old Display/Graphics/Sound
categories, all original setting rows reachable by
controller, including Linear Filter, Internal resolution and Music/SFX
volumes. Exercise representative toggles and save/reopen round-trip with
existing settings. A focused hidden/headless UI check and capture suffice;
do not repeat the full S3 matrix. Build under the shared heavy lock with
≤3 jobs and use at most one runtime. Ordinary grouping changes need no new
gameplay regression suite beyond checks justified by affected code.

Update user-facing menu-path documentation and brittle scripted category
navigation touched by the change. Report the old-to-new row inventory,
commands/exits, capture path, preference persistence and remaining limitations
with worker_done; do not claim owner acceptance before a playtest.
