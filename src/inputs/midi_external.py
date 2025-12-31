"""External USB-MIDI input handler.

Processes MIDI events from external controllers or keyboards
connected via USB-MIDI.
"""

import mido
from typing import Callable, Optional
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from util.logging import get_logger

logger = get_logger('midi_input')


class MidiInput:
    """Handles MIDI input from external devices."""
    
    def __init__(self, port_name: str, callback: Callable[[mido.Message], None]):
        """Initialize MIDI input handler.
        
        Args:
            port_name: ALSA MIDI port name (e.g., "U6MIDI Pro:U6MIDI Pro MIDI 1 20:0")
            callback: Function to call when MIDI message is received
        """
        self.port_name = port_name
        self.callback = callback
        self.port: Optional[mido.ports.BaseInput] = None
        self.running = False
        
    def start(self):
        """Open the MIDI input port and start receiving messages."""
        try:
            logger.info(f"Opening MIDI input port: {self.port_name}")
            self.port = mido.open_input(self.port_name)
            self.running = True
            logger.info(f"MIDI input port opened successfully")
        except Exception as e:
            logger.error(f"Failed to open MIDI input port: {e}")
            raise
    
    def process_messages(self):
        """Process incoming MIDI messages (blocking call)."""
        if not self.port or not self.running:
            logger.warning("MIDI input not started")
            return
        
        logger.info("Starting MIDI message processing loop")
        try:
            for msg in self.port:
                if not self.running:
                    break
                self.callback(msg)
        except KeyboardInterrupt:
            logger.info("MIDI input interrupted by user")
        except Exception as e:
            logger.error(f"Error processing MIDI messages: {e}")
            raise
    
    def stop(self):
        """Stop receiving MIDI messages and close the port."""
        self.running = False
        if self.port:
            logger.info("Closing MIDI input port")
            self.port.close()
            self.port = None

