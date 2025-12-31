"""MIDI output to organ ranks.

Sends note on/off and control messages to physical or
virtual ranks via MIDI.
"""

import mido
from typing import Optional
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from util.logging import get_logger

logger = get_logger('midi_output')


class MidiOutput:
    """Handles MIDI output to external devices."""
    
    def __init__(self, port_name: str):
        """Initialize MIDI output handler.
        
        Args:
            port_name: ALSA MIDI port name (e.g., "U6MIDI Pro:U6MIDI Pro MIDI 2 20:1")
        """
        self.port_name = port_name
        self.port: Optional[mido.ports.BaseOutput] = None
        
    def start(self):
        """Open the MIDI output port."""
        try:
            logger.info(f"Opening MIDI output port: {self.port_name}")
            self.port = mido.open_output(self.port_name)
            logger.info(f"MIDI output port opened successfully")
        except Exception as e:
            logger.error(f"Failed to open MIDI output port: {e}")
            raise
    
    def send_message(self, msg: mido.Message):
        """Send a MIDI message to the output port.
        
        Args:
            msg: MIDI message to send
        """
        if not self.port:
            logger.warning("MIDI output port not open")
            return
        
        try:
            self.port.send(msg)
            logger.debug(f"Sent MIDI: {msg}")
        except Exception as e:
            logger.error(f"Failed to send MIDI message: {e}")
    
    def stop(self):
        """Close the MIDI output port."""
        if self.port:
            logger.info("Closing MIDI output port")
            self.port.close()
            self.port = None

