# Memory notes carried over from the desktop-side Claude session

These are the persistent "memory" entries the desktop Claude Code session
had built up about this project and the user's standing instructions for
it. They're reproduced here verbatim/near-verbatim so a Claude session on
this T480s (which won't have access to the desktop's local memory files)
still has them. Treat these as durable facts/instructions, not one-off
context.

## The core standing instruction (most important — repeat this to yourself before doing anything else)

The user wants **macOS 27 "Golden Gate"'s real, usable desktop environment**
— rendered by Apple's own WindowServer, not a mockup — actually visible on
the T480s's screen. They have said this many times, with increasing
intensity, across the whole project:

- "BRO JUST KEEP GOING TIL ITS ON MY SCREEN, THE USABLE DESKTOP ENVIRONMENT
  MACOS 27 ITSELF"
- "save to memory and go and dont stop til its finsihed, even massive stuff
  u find/bugs/fixes. jsut keep going. dont ask querstions, figure out stuff
  yourself. do not hand back that prompt til i see golden gate on the
  t480s screen"
- "no, we WILL AND ABSOLUTELY WILL NO MATTER HOW LONG IT TAKES WE WILL AND
  WILL MAKE MACOS GOLDEN GATE ITSELF RUN ON THIS." (said when offered a
  fake/simulated desktop as a shortcut — they explicitly rejected that and
  never want it offered again)

**Practical meaning**: work continuously and autonomously. Don't stop to
ask permission or report routine status. Don't propose shortcuts that fake
the end result. Don't consider the task done until a real Golden Gate
desktop is actually rendering on this machine's screen. Save real findings
(including bugs, dead ends, and partial progress) as you go rather than
only at the end — the user wants a durable record even of "massive stuff"
that doesn't immediately lead anywhere, not just final wins.

## Who the user is / how they like to work (general, not Golden-Gate-specific, but useful context)

- Runs HackMate, an open-source Python hackintosh-automation tool (87
  stars at last count, 1000+ downloads, ~v1.4.0). Golden Gate is a
  moonshot/showcase project tied to a YouTuber (RAM, channelramble)
  challenge/review of HackMate.
- Prefers autonomous execution: when told "don't ask, don't stop," that
  means actually run unattended for as long as it takes and resolve
  ambiguity yourself rather than checking in.
- Wants HackMate feature work pushed straight to `main` (no feature
  branches) in that repo specifically — not necessarily relevant to this
  repo, but worth knowing if you end up touching HackMate itself.
- Is currently in middle school — scope any budget/resource suggestions
  realistically, but this has no bearing on the technical ambition of the
  project itself, which the user wants pursued fully regardless of
  difficulty.
- Delegates sub-tasks to a local Codex CLI instance when that's
  cheaper/faster — `CODEX_HANDOFF.md` in this repo is an example of a
  handoff written for that workflow. Not required reading, but there if
  useful.
- Does not want fake/mocked results presented as real (see the "no
  shortcuts" instruction above) — if something isn't actually working,
  say so plainly rather than papering over it.

## Project-specific facts worth remembering

- Target machine: **this T480s** (Intel, already dual-boots/runs a working
  hackintosh Tahoe install separately from this project's QEMU work).
- The whole approach is full ARM64 software emulation (QEMU/TCG) — there
  is no real Apple Silicon involved anywhere, and no hardware
  acceleration (no HVF/KVM). This is why performance is a constant
  factor and why the `-icount` timer bug (see `FORCLAUDE.md`) is such a
  fundamental, structural issue rather than a one-off glitch.
- RAM's video/review deadline exists but the user has explicitly said
  time is not a constraint they want traded against getting the *real*
  thing working: "no matter how long it takes."
- See `FORCLAUDE.md` in this same repo for the full technical handoff
  (current blocker, exact commands, proven techniques, what's already
  ruled out). This file is about durable instructions/context; that one
  is about the live technical state.
