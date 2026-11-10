# Task 37: intermittent missing instruments in race-menu music

**Status: explicitly deferred by the owner to another session.** No worker,
investigation, code fix or CI run should start from this note alone.

After manually testing the current local macOS build containing the S3 Linear
Filter and unified runtime menu, the owner approved those changes (“Está tudo
certo”), then reported that some instruments sometimes seem absent in the
race-menu music. His follow-up was to commit the filter/menu work and leave
the instrument question for another session.

The exact screen/song and sequence are not yet identified: “menu de corrida”
must not be silently equated with the title, shop, track intro or race itself.
No recording or instrument/channel diagnosis exists yet.

Useful facts already checked, not a root-cause claim:

- Comparing old draft source `a205759` to new draft `87e926b`, the audio mixer,
  BOTH routing and audio patches did not change. The `tg2_options.c` addition
  only maps/orders runtime-menu category names; it changes no audio setter.
- The local build's saved settings at the report were RACE SOUND **BOTH**,
  master/Music/SFX volumes **100%**, bypass filter Off; the withdrawn Clean FM
  and Clean engine samples sections were absent.
- Earlier post-v0.1.0 audio work exists (Music/SFX faders and live switching;
  Clean FM/DAC options later removed). Do not imply there has never been any
  audio change merely because the two latest drafts share audio code.
- `docs/AUDIO.md` documents prior BOTH/routing/state issues and a separate
  Auckland re-attack observation. Neither is established as this report's
  cause. Confirm the exact screen and first divergence before linking them.

Next session: identify the screen/track and reproduction sequence with the
owner, preserve his settings, then use the normal retrospective audio/state
evidence and a same-input reference. Follow AGENTS.md resource/ROM rules and
stream any WAV analysis. Keep this separate from the already approved
filter/menu work and do not reopen S3 visual acceptance without new evidence.
