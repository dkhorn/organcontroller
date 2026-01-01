# Organ Controller Quick Start

## Current Setup

### Hardware Configuration
- **Input**: U6MIDI Pro MIDI 1 (port 20:0)
- **Output 1**: U6MIDI Pro MIDI 2 (port 20:1) - Hardware output
- **Output 2**: FS_Virtual (128:0) - Software synthesizer

### What's Working

✅ **MIDI Passthrough**: Input from port 1 is routed to both outputs simultaneously  
✅ **FluidSynth**: Software synthesizer running with organ soundfont  
✅ **Logging**: All MIDI messages logged to console  
✅ **Clean Shutdown**: Ctrl+C now exits gracefully (no more kill -9 needed!)  

## Running Manually

### Start FluidSynth
```bash
cd /home/daniel/organcontroller
./scripts/start_fluidsynth.sh
```

### Start Organ Controller
```bash
cd /home/daniel/organcontroller
./scripts/start_master.sh
```

### Stop
Press `Ctrl+C` in the controller terminal

## Running as System Services

See [systemd/README.md](systemd/README.md) for installation instructions.

## Testing

1. Connect a MIDI keyboard to **U6MIDI Pro MIDI 1**
2. Connect a MIDI device/synth to **U6MIDI Pro MIDI 2** (optional)
3. Play notes - you should:
   - See them logged in the console
   - Hear them from FluidSynth (if speakers connected)
   - See them output to hardware port 2 (if connected)

## Configuration

Edit [config/midi_ports.yaml](config/midi_ports.yaml) to change port assignments.

## Architecture

```
┌──────────────────┐
│  MIDI Input      │
│  (U6MIDI Port 1) │
└────────┬─────────┘
         │
         ▼
┌────────────────────┐
│  Organ Controller  │
│  (logs messages)   │
└────────┬───────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐  ┌─────────────┐
│Hardware│  │ FluidSynth  │
│Port 2  │  │ (Software)  │
└────────┘  └─────────────┘
```
