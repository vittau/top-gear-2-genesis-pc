# PLAN: Top Gear 2 (Sega Genesis) - PC Native Recompilation Project

## 1. Project Goal

Develop a native PC port (Windows/Linux) of **Top Gear 2 (Sega Genesis)** using static recompilation techniques based on the `mstan/segagenesisrecomp` ecosystem. The final executable must run natively without an emulator, featuring **true adaptive widescreen (16:9+)** support, modern inputs (SDL2), and clean separation of game logic from original hardware constraints.

---

## 2. Technical Stack & Dependencies

* **Recompilation Core:** `mstan/segagenesisrecomp` (M68K instruction to C11 translator).
* **Reverse Engineering Environment:** Ghidra (with Motorola 68000 processor module and custom `segagenesisrecomp` scripts).
* **Build System:** CMake (C11 codebase compilation).
* **Backend & I/O:** SDL2 / OpenGL (provided by the `recomp-ui` framework).
* **Target Architecture:** Motorola 68000 (Game ROM) $\rightarrow$ Native x86_64 / ARM64 C11 executable.

---

## 3. Phase-by-Phase Execution Roadmap

### Phase 1: Environment Setup & Tooling Compilation

* [ ] Clone the `mstan/segagenesisrecomp` repository recursively.
* [ ] Compile `GenesisRecomp.exe` standalone compiler via CMake.
* [ ] Install Ghidra and import the `segagenesisrecomp` helper scripts.
* [ ] Verify the setup by processing a known test ROM (e.g., Sonic 1) to ensure the C11 conversion toolchain works.

### Phase 2: Reverse Engineering & ROM Mapping (Ghidra)

* [ ] Import a clean, verified USA/Europe ROM of *Top Gear 2* (Genesis) into Ghidra.
* [ ] Apply basic automated analysis for the M68K CPU architecture.
* [ ] Map the hardware vector table and memory boundaries (RAM, VRAM, VDP registers).
* [ ] Isolate the game loop entry point (`VBlank` interrupts and main execution loop).
* [ ] Target and label critical functional subsystems:
  * `Draw_Road_Subroutine`: The pseudo-3D line-by-line raster effect engine.
  * `Object_Spawning`: Sprites for rival cars, roadside hazards, and signs.
  * `UI_Rendering`: HUD layout, speedometer, position, and text rendering.
  * `Audio_Driver`: Sound effects and music interaction with the Z80/YM2612 wrapper.

### Phase 3: Initial Static Recompilation (Vanilla Baseline)

* [ ] Export the mapped symbol file (`.json`/`.symbols`) from Ghidra.
* [ ] Run `GenesisRecomp.exe` targeting the Top Gear 2 ROM and symbol map.
* [ ] Resolve initial translation errors, manual symbol definitions, and unmapped branches.
* [ ] Compile the output C11 code using the `recomp-ui` runtime backend.
* [ ] Achieve a **1:1 accurate 4:3 baseline boot** running natively on PC.

### Phase 4: Pseudo-3D Engine Modification & Widescreen Implementation

* [ ] Analyze the decompiled rendering loop that draws the track projection.
* [ ] Modify the VDP H-Blank and line-shifting logic to calculate rendering math beyond the standard 320px width barrier.
* [ ] Implement **Adaptive Aspect Ratio Scaling**:
  * Adjust camera projection matrix coefficients to pull additional scenery into view laterally.
  * Increase the horizontal horizontal horizontal clipping bounds for 3D road lines.
  * Patch object rendering bounds to prevent cars and signs from popping in at the 4:3 edges.
* [ ] Pin the HUD elements (speedometer, position) to the modern display edges or keep them centered at 4:3 via an overlay flag.

### Phase 5: Polish, Audio, and Feature Enhancements

* [ ] Integrate native controller mapping, analog stick handling, and deadzones via SDL2.
* [ ] Ensure clean audio execution using the clean-room VDP/sound backend provided by `segagenesisrecomp`.
* [ ] Add quality-of-life options (e.g., standard 60 FPS uncap validation, resolution switching, save-state hooks).

---

## 4. Immediate Prompts for Agent Execution

Use these atomic instructions sequentially to drive your AI programming agents:

1. **Prompt 1 (Setup):** *"Analyze the `mstan/segagenesisrecomp` structure. Write a script to automatically pull the codebase, verify CMake prerequisites for my environment, and compile the `GenesisRecomp` tool binary."*
2. **Prompt 2 (Analysis Prep):** *"Generate a Ghidra Python automation script configured for the Sega Genesis memory map (M68K). The script should automatically flag common hardware I/O regions ($C00000-$C00004 for VDP) and create entry labels for the standard Sega vector table."*
3. **Prompt 3 (Engine Insight):** *"Explain how typical Genesis racing games handle pseudo-3D horizontal scrolling arrays per scanline. Write a C simulation of a scanline-shifted road rendering algorithm to help me identify these patterns in the decompiled assembly code."*
