# Rank Addressing & Registration System

## Overview

The organ controller manages both physical pipe ranks and virtual (digital) ranks, each with a unique MIDI address in the format: `device:port:channel`

## Physical Ranks (Hardware)

All physical ranks are mapped to **U6MIDI Pro MIDI 3 (port 20:2)** with different channels:

| Rank ID | Name | Channel | Description |
|---------|------|---------|-------------|
| M1 | Principal Chorus | 0 | 61-note principal (16', 8', 4', 2') |
| M2 | Dulciana | 1 | Soft string for Swell |
| M3 | Voix Celeste | 2 | 49-pipe sharp celeste |
| M4 | Salicional | 3 | String rank (8' & 4') |
| M5 | High String/Piccolo | 4 | Enclosed in Swell |
| W1 | Open Flute | 5 | 85-pipe open flute |
| W2-A | Bourdon (Unenclosed) | 6 | Great/Pedal bourdon |
| W2-B | Gedackt (Swell) | 7 | Swell-only, no borrowing |
| W3 | Tibia Bass | 8 | 24-pipe pedal bass |
| R1 | Subbass (Free Reed) | 9 | 16' free reed |

## Virtual Ranks (FluidSynth)

Virtual ranks use **FluidSynth (port 128:0)** with one rank per channel. Each channel is pre-loaded with a specific program (instrument):

| Channel | Program | Rank | Description |
|---------|---------|------|-------------|
| 0 | 0 | Great Mixture | IV-V ranks |
| 1 | 1 | Swell Mixture | III ranks |
| 2 | 2 | Swell Fifteenth | 2' principal |
| 3 | 3 | Pedal Mixture | IV ranks |
| 4 | 4 | Great Trumpet | 8' chorus reed |
| 5 | 5 | Great Clarion | 4' reed |
| 6 | 6 | Swell Trumpet | 8' enclosed reed |
| 7 | 7 | Swell Oboe | Solo reed |
| 8 | 8 | Choir Nazard | 2-2/3' mutation |
| 9 | 9 | Choir Tierce | 1-3/5' mutation |
| 10 | 10 | Choir Larigot | 1-1/3' mutation |
| 11 | 11 | Choir Cymbale | III mixture |
| 12 | 12 | Choir Clarinet | Solo reed |
| 13 | 13 | Choir Vox Humana | Tremmed voice |
| 14 | 14 | Pedal Trombone | 16' heavy reed |
| 15 | 15 | Pedal Trumpet | 8' pedal reed |

## Initialization Sequence

On startup, the controller:

1. Opens three MIDI output ports:
   - `hardware` (port 2) - for testing/passthrough
   - `physical_ranks` (port 3) - for all physical pipe ranks
   - `fluidsynth` (virtual) - for all digital voices

2. Sends program change messages to FluidSynth:
   - Each channel receives its assigned program number
   - This loads the correct soundfont preset for each rank

3. Begins processing input MIDI messages

## Stop Registration (Future)

When a stop is drawn, the controller will:
- Look up which rank(s) that stop uses
- Route incoming MIDI notes to those rank addresses
- Handle extensions, borrowing, and unification
- Apply expression (swell box) and tremulant as needed

## Benefits of This System

- **Scalability**: Easy to add new ranks
- **Flexibility**: Physical and virtual ranks treated uniformly
- **Clarity**: Each rank has one unique address
- **Efficiency**: FluidSynth uses all 16 channels optimally
- **Maintainability**: Configuration is human-readable YAML
