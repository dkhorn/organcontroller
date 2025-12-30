#!/bin/bash
# Start FluidSynth with appropriate configuration
# Loads soundfonts and configures MIDI routing

fluidsynth -a alsa -m alsa_seq -r 48000 -o audio.alsa.device=plughw:0,0 -o audio.period-size=128 -o audio.periods=3 /home/daniel/synth/jeuxdorgues21.SF2