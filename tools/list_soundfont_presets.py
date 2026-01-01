#!/usr/bin/env python3
"""List all programs/presets in a SoundFont file."""

import sys
import subprocess
import re

def list_soundfont_presets(sf_path):
    """Use FluidSynth to list all presets in a soundfont."""
    
    # Start FluidSynth and send 'inst 1' command to list presets
    cmd = ['fluidsynth', '-a', 'alsa', '-m', 'alsa_seq', sf_path]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Send commands to FluidSynth
        stdout, stderr = proc.communicate(input="inst 1\nquit\n", timeout=5)
        
        # Parse the output for preset listings
        # Format is typically: "000-000 preset_name"
        presets = []
        for line in stdout.split('\n'):
            # Look for lines with preset info: "bank-prog name"
            match = re.match(r'^\s*(\d+)-(\d+)\s+(.+)$', line)
            if match:
                bank, prog, name = match.groups()
                presets.append({
                    'bank': int(bank),
                    'program': int(prog),
                    'name': name.strip()
                })
        
        return presets
        
    except subprocess.TimeoutExpired:
        proc.kill()
        return []
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: list_soundfont_presets.py <soundfont.sf2>")
        sys.exit(1)
    
    sf_path = sys.argv[1]
    presets = list_soundfont_presets(sf_path)
    
    if not presets:
        print("No presets found or error reading soundfont")
        sys.exit(1)
    
    print(f"\nPresets in {sf_path}:\n")
    print(f"{'Bank':<6} {'Prog':<6} {'Name'}")
    print("-" * 60)
    
    for preset in presets:
        print(f"{preset['bank']:<6} {preset['program']:<6} {preset['name']}")
