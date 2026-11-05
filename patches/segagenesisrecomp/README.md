# Engine patches

- `0001-preserve-irq-register-effects.patch`: preserve general-register changes made by guest ISRs, including raster pointers advanced between H-interrupts.

`tools/build-linux.sh` applies these idempotently through
`tools/apply-engine-patches.sh`. The submodule stays pinned to the upstream
commit; local fixes remain visible as its applied working-tree diff.
