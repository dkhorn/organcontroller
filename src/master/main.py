"""Main entry point for the organ master controller.

Initializes all subsystems, starts input/output threads,
and runs the main event loop.
"""

import sys
import signal
import logging
from pathlib import Path
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from util.logging import setup_logging, get_logger
from inputs.midi_external import MidiInput
from outputs.midi_ranks import MidiOutput

logger = get_logger('main')


class OrganController:
    """Main organ controller service."""
    
    def __init__(self, config_path: str = "config/midi_ports.yaml"):
        """Initialize the organ controller.
        
        Args:
            config_path: Path to MIDI ports configuration file
        """
        self.config_path = config_path
        self.midi_input: MidiInput = None
        self.midi_output: MidiOutput = None
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def load_config(self) -> dict:
        """Load MIDI port configuration from YAML file.
        
        Returns:
            Configuration dictionary
        """
        config_file = Path(__file__).parent.parent.parent / self.config_path
        logger.info(f"Loading configuration from: {config_file}")
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded successfully")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def on_midi_message(self, msg):
        """Callback for received MIDI messages.
        
        Args:
            msg: MIDI message from input
        """
        # Log the received message
        logger.info(f"Received: {msg}")
        
        # Pass through to output
        if self.midi_output:
            self.midi_output.send_message(msg)
    
    def start(self):
        """Start the organ controller service."""
        logger.info("=== Organ Controller Starting ===")
        
        # Load configuration
        config = self.load_config()
        input_port = config.get('input_port')
        output_port = config.get('output_port')
        
        if not input_port or not output_port:
            logger.error("Input or output port not configured")
            return
        
        logger.info(f"Input port: {input_port}")
        logger.info(f"Output port: {output_port}")
        
        # Initialize MIDI output
        self.midi_output = MidiOutput(output_port)
        self.midi_output.start()
        
        # Initialize MIDI input with callback
        self.midi_input = MidiInput(input_port, self.on_midi_message)
        self.midi_input.start()
        
        # Start processing (this blocks)
        self.running = True
        logger.info("=== Organ Controller Running ===")
        self.midi_input.process_messages()
    
    def stop(self):
        """Stop the organ controller service."""
        if not self.running:
            return
        
        logger.info("=== Organ Controller Stopping ===")
        self.running = False
        
        if self.midi_input:
            self.midi_input.stop()
        
        if self.midi_output:
            self.midi_output.stop()
        
        logger.info("=== Organ Controller Stopped ===")


def main():
    """Main entry point."""
    # Setup logging
    setup_logging(level=logging.INFO)
    
    # Create and start controller
    controller = OrganController()
    
    try:
        controller.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        controller.stop()


if __name__ == "__main__":
    main()

