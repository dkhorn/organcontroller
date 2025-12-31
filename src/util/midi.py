"""MIDI utility functions.

Common MIDI message parsing, formatting, and constants.
"""

from typing import Tuple, Optional


# MIDI Message Type Constants
NOTE_OFF = 0x80
NOTE_ON = 0x90
POLY_AFTERTOUCH = 0xA0
CONTROL_CHANGE = 0xB0
PROGRAM_CHANGE = 0xC0
CHANNEL_AFTERTOUCH = 0xD0
PITCH_BEND = 0xE0

# System Common Messages
SYSEX_START = 0xF0
SYSEX_END = 0xF7


def parse_midi_message(msg_bytes: bytes) -> Tuple[str, int, Optional[int], Optional[int]]:
    """Parse a MIDI message into its components.
    
    Args:
        msg_bytes: Raw MIDI message bytes
        
    Returns:
        Tuple of (message_type, channel, data1, data2)
    """
    if not msg_bytes:
        return ("unknown", 0, None, None)
    
    status = msg_bytes[0]
    msg_type = status & 0xF0
    channel = status & 0x0F
    
    data1 = msg_bytes[1] if len(msg_bytes) > 1 else None
    data2 = msg_bytes[2] if len(msg_bytes) > 2 else None
    
    type_names = {
        NOTE_OFF: "note_off",
        NOTE_ON: "note_on",
        POLY_AFTERTOUCH: "poly_aftertouch",
        CONTROL_CHANGE: "control_change",
        PROGRAM_CHANGE: "program_change",
        CHANNEL_AFTERTOUCH: "channel_aftertouch",
        PITCH_BEND: "pitch_bend",
    }
    
    return (type_names.get(msg_type, "unknown"), channel, data1, data2)


def format_midi_message(msg_bytes: bytes) -> str:
    """Format a MIDI message for logging.
    
    Args:
        msg_bytes: Raw MIDI message bytes
        
    Returns:
        Human-readable string representation
    """
    msg_type, channel, data1, data2 = parse_midi_message(msg_bytes)
    
    if msg_type == "note_on" and data2 == 0:
        msg_type = "note_off"
    
    parts = [msg_type.upper(), f"ch={channel}"]
    
    if data1 is not None:
        if msg_type in ("note_on", "note_off"):
            parts.append(f"note={data1}")
            if data2 is not None:
                parts.append(f"vel={data2}")
        elif msg_type == "control_change":
            parts.append(f"cc={data1}")
            if data2 is not None:
                parts.append(f"val={data2}")
        else:
            parts.append(f"d1={data1}")
            if data2 is not None:
                parts.append(f"d2={data2}")
    
    return " ".join(parts)

