#!/bin/bash
# Start FluidSynth with appropriate configuration
# Loads soundfonts and configures MIDI routing

# -a alsa: Use ALSA audio driver
# -m alsa_seq: Use ALSA sequencer for MIDI (creates virtual port)
# -r 48000: Sample rate
# -o audio.alsa.device: Specify audio output device
# -o audio.period-size: Buffer size for low latency
# -o audio.periods: Number of periods
# -o midi.portname: Name for the virtual MIDI port

fluidsynth \
  -a pulseaudio \
  -m alsa_seq \
  -r 48000 \
  -g 1.0 \
  -o audio.period-size=128 \
  -o audio.periods=3 \
  -o midi.portname="FS_Virtual" \
  /home/daniel/organcontroller/soundfonts/jeuxdorgues21.SF2