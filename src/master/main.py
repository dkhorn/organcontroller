"""Main entry point for the organ master controller.

Initializes all subsystems, starts input/output threads,
and runs the main event loop.
"""

import sys
import signal
import logging
import argparse
import threading
from pathlib import Path
import yaml
import mido

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from util.logging import setup_logging, get_logger
from inputs.midi_external import MidiInput
from outputs.midi_ranks import MidiOutput
from logic.stops import StopRouter
from logic.input_mapper import InputMapper

logger = get_logger('main')


class OrganController:
    """Main organ controller service."""
    
    def __init__(self, config_path: str = "config/midi_ports.yaml", 
                 ranks_config_path: str = "config/ranks.yaml",
                 stops_config_path: str = "config/stops.yaml",
                 input_map_config_path: str = "config/input_map.yaml",
                 daemon_mode: bool = False):
        """Initialize the organ controller.
        
        Args:
            config_path: Path to MIDI ports configuration file
            ranks_config_path: Path to ranks configuration file
            stops_config_path: Path to stops configuration file
            input_map_config_path: Path to input mapping configuration file
            daemon_mode: If True, run as daemon; if False, run interactive mode
        """
        self.config_path = config_path
        self.ranks_config_path = ranks_config_path
        self.stops_config_path = stops_config_path
        self.input_map_config_path = input_map_config_path
        self.daemon_mode = daemon_mode
        self.midi_input: MidiInput = None
        self.midi_outputs: dict = {}  # Multiple outputs
        self.ranks_config: dict = {}
        self.stops_config: dict = {}
        self.stop_router: StopRouter = None  # Stop routing engine
        self.input_mapper: InputMapper = None  # Input routing engine
        self.active_stops: set = set()  # Track which stops are drawn
        self.active_keys: dict = {}  # Track pressed keys: (division, note) -> timestamp
        self.active_rank_notes: dict = {}  # Track rank notes: (output, channel, note) -> (rank_id, timestamp)
        self.running = False
        self._shutdown_requested = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        if self._shutdown_requested:
            logger.warning("Shutdown already in progress...")
            return
        self._shutdown_requested = True
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        if self.midi_input:
            self.midi_input.running = False
    
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
    
    def load_ranks_config(self) -> dict:
        """Load ranks configuration from YAML file.
        
        Returns:
            Ranks configuration dictionary
        """
        ranks_file = Path(__file__).parent.parent.parent / self.ranks_config_path
        logger.info(f"Loading ranks configuration from: {ranks_file}")
        
        try:
            with open(ranks_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Ranks configuration loaded: {len(config.get('physical_ranks', {}))} physical, {len(config.get('virtual_ranks', {}))} virtual")
            return config
        except Exception as e:
            logger.error(f"Failed to load ranks configuration: {e}")
            raise
    
    def load_stops_config(self) -> dict:
        """Load stops configuration from YAML file.
        
        Returns:
            Stops configuration dictionary
        """
        stops_file = Path(__file__).parent.parent.parent / self.stops_config_path
        logger.info(f"Loading stops configuration from: {stops_file}")
        
        try:
            with open(stops_file, 'r') as f:
                config = yaml.safe_load(f)
            # Count total stops across all divisions
            total_stops = sum(len(config.get(div, {})) for div in ['great', 'swell', 'choir', 'pedal'])
            logger.info(f"Stops configuration loaded: {total_stops} stops across 4 divisions")
            return config
        except Exception as e:
            logger.error(f"Failed to load stops configuration: {e}")
            raise
    
    def initialize_outputs(self):
        """Initialize outputs with default settings (e.g., select instruments)."""
        import mido
        import time
        
        # Load ranks configuration to know what programs to load
        virtual_ranks = self.ranks_config.get('virtual_ranks', {})
        
        # Initialize virtual ranks with their assigned programs
        if virtual_ranks:
            logger.info("Initializing virtual ranks...")
            
            # Process each virtual rank
            for rank_id, rank_info in virtual_ranks.items():
                midi_addr = rank_info.get('midi_address', '')
                program = rank_info.get('program')
                
                if not midi_addr or program is None:
                    continue
                
                # Parse address to extract channel
                parts = midi_addr.split(':')
                if len(parts) < 4:
                    continue
                
                try:
                    channel = int(parts[-1])
                except ValueError:
                    continue
                
                # Determine output name using same logic as stops.py
                output_name = None
                if 'FS_Virtual2' in midi_addr or '129:0' in midi_addr:
                    output_name = 'fluidsynth2'
                elif 'FS_Virtual' in midi_addr or '128:0' in midi_addr:
                    output_name = 'fluidsynth'
                elif 'U6MIDI Pro MIDI 3' in midi_addr or '20:2' in midi_addr:
                    output_name = 'physical_ranks'
                elif 'U6MIDI Pro MIDI 2' in midi_addr or '20:1' in midi_addr:
                    output_name = 'hardware'
                
                if output_name and output_name in self.midi_outputs:
                    target_output = self.midi_outputs[output_name]
                    logger.info(f"  {output_name} ch{channel}: Program {program} ({rank_info['name']})")
                    msg = mido.Message('program_change', program=program, channel=channel)
                    target_output.send_message(msg)
                    time.sleep(0.01)  # Small delay between program changes
                else:
                    logger.warning(f"  Output '{output_name}' not found for rank {rank_id}")
            
            logger.info("Virtual ranks initialized")
    
    def on_midi_message(self, msg):
        """Callback for received MIDI messages.
        
        Args:
            msg: MIDI message from input
        """
        if not self.running:
            return
        
        # Log the received message
        logger.debug(f"Received: {msg}")
        
        # Route through input mapper
        if self.input_mapper:
            try:
                self.input_mapper.process_message(msg)
            except Exception as e:
                logger.error(f"Error processing MIDI message: {e}", exc_info=True)
    
    def start(self):
        """Start the organ controller service."""
        logger.info("=== Organ Controller Starting ===")
        
        # Load configuration
        config = self.load_config()
        self.ranks_config = self.load_ranks_config()
        self.stops_config = self.load_stops_config()
        
        input_port = config.get('input_port')
        output_ports = config.get('output_ports', {})
        
        if not input_port:
            logger.error("Input port not configured")
            return
        
        if not output_ports:
            logger.error("No output ports configured")
            return
        
        logger.info(f"Input port: {input_port}")
        
        # Initialize MIDI outputs
        for name, port in output_ports.items():
            try:
                logger.info(f"Initializing output '{name}': {port}")
                output = MidiOutput(port)
                output.start()
                self.midi_outputs[name] = output
            except Exception as e:
                logger.warning(f"Could not open output '{name}': {e}")
        
        if not self.midi_outputs:
            logger.error("No output ports could be opened")
            return
        
        # Initialize outputs with default settings
        self.initialize_outputs()
        
        # Initialize stop router
        self.stop_router = StopRouter(self.stops_config, self.ranks_config, self.midi_outputs, self)
        logger.info("Stop router initialized")
        
        # Build stop name lookup map (case-insensitive)
        self.stop_lookup = {}  # lowercase stop_name -> (division, STOP_NAME)
        for division in ['great', 'swell', 'choir', 'pedal']:
            if division in self.stops_config:
                for stop_name in self.stops_config[division].keys():
                    self.stop_lookup[stop_name.lower()] = (division, stop_name)
        logger.info(f"Stop lookup map built: {len(self.stop_lookup)} stops")
        
        # Initialize input mapper
        input_map_path = Path(__file__).parent.parent.parent / self.input_map_config_path
        self.input_mapper = InputMapper(str(input_map_path), self.stop_router, self.stops_config, self)
        logger.info("Input mapper initialized")
        
        # Initialize MIDI input with callback
        self.midi_input = MidiInput(input_port, self.on_midi_message)
        self.midi_input.start()
        
        # Start processing
        self.running = True
        logger.info("=== Organ Controller Running ===")
        
        try:
            if self.daemon_mode:
                # Daemon mode: just process MIDI messages
                self.midi_input.process_messages()
            else:
                # Interactive mode: start MIDI in background thread and run command loop
                midi_thread = threading.Thread(target=self.midi_input.process_messages, daemon=True)
                midi_thread.start()
                self.run_interactive_mode()
        finally:
            self.stop()
    
    def run_interactive_mode(self):
        """Run the interactive command loop."""
        import readline
        import os
        import atexit
        
        # Set up history file
        history_file = os.path.expanduser('~/.organ_controller_history')
        history_length = 1000
        
        # Load history if it exists
        if os.path.exists(history_file):
            try:
                readline.read_history_file(history_file)
                logger.debug(f"Loaded command history from {history_file}")
            except Exception as e:
                logger.warning(f"Could not load history file: {e}")
        
        # Set history length
        readline.set_history_length(history_length)
        
        # Register function to save history on exit
        def save_history():
            try:
                readline.write_history_file(history_file)
                logger.debug(f"Saved command history to {history_file}")
            except Exception as e:
                logger.warning(f"Could not save history file: {e}")
        
        atexit.register(save_history)
        
        print("\n" + "="*60)
        print("ORGAN CONTROLLER - Interactive Mode")
        print("="*60)
        print("Type 'help' for available commands")
        print("Use UP/DOWN arrows to recall previous commands\n")
        
        while self.running:
            try:
                cmd_line = input("> ").strip()
                if not cmd_line:
                    continue
                
                parts = cmd_line.split()
                cmd = parts[0].lower()
                args = parts[1:]
                
                self.process_command(cmd, args)
                
            except EOFError:
                print("\nReceived EOF, exiting...")
                break
            except KeyboardInterrupt:
                print("\nInterrupted by user, exiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def process_command(self, cmd: str, args: list):
        """Process an interactive command.
        
        Args:
            cmd: Command name
            args: Command arguments
        """
        if cmd == "help":
            self.cmd_help()
        elif cmd == "stop_on":
            self.cmd_stop_on(args)
        elif cmd == "stop_off":
            self.cmd_stop_off(args)
        elif cmd == "key_on":
            self.cmd_key_on(args)
        elif cmd == "key_off":
            self.cmd_key_off(args)
        elif cmd == "all_clear":
            self.cmd_all_clear()
        elif cmd == "status":
            self.cmd_status()
        elif cmd == "state":
            self.cmd_state(args)
        elif cmd == "list_stops":
            self.cmd_list_stops(args)
        elif cmd == "exit" or cmd == "quit":
            print("Exiting...")
            self.running = False
        else:
            print(f"Unknown command: {cmd}")
            print("Type 'help' for available commands")
    
    def cmd_help(self):
        """Display help for available commands."""
        print("""
Available Commands:
  help                      - Show this help message
  stop_on STOP_NAME         - Turn on a stop (e.g., great_principal_8 or GREAT_PRINCIPAL_8)
  stop_off STOP_NAME        - Turn off a stop
  key_on MANUAL NOTE        - Simulate key press (MANUAL: G/S/C/P, NOTE: 0-127)
  key_off MANUAL NOTE       - Simulate key release
  all_clear                 - Turn off all stops
  status                    - Show active stops and system status
  state [keys|notes]        - Show state: keys pressed, rank notes playing, or both
  list_stops [DIVISION]     - List all stops (optionally filter by division)
  exit, quit                - Exit the controller

Examples:
  stop_on great_principal_8
  stop_on SWELL_MIXTURE
  key_on G 60               - Middle C on Great manual
  key_on P 36               - C (pedal) on Pedal board
  list_stops great          - List all Great stops
        """)
    
    def cmd_stop_on(self, args: list):
        """Turn on a stop."""
        if not args:
            print("Usage: stop_on STOP_NAME")
            print("Example: stop_on great_principal_8 or stop_on GREAT_PRINCIPAL_8")
            return
        
        stop_name = args[0].lower()
        
        if stop_name not in self.stop_lookup:
            print(f"Unknown stop: {args[0]}")
            print("Use 'list_stops' to see all available stops")
            return
        
        division, actual_stop_name = self.stop_lookup[stop_name]
        full_id = f"{division}:{actual_stop_name}"
        
        if self.stop_router.activate_stop(full_id):
            stop_info = self.stops_config[division][actual_stop_name]
            print(f"ON: {stop_info['name']} ({actual_stop_name})")
        else:
            print(f"Failed to activate stop: {full_id}")
    
    def cmd_stop_off(self, args: list):
        """Turn off a stop."""
        if not args:
            print("Usage: stop_off STOP_NAME")
            print("Example: stop_off great_principal_8 or stop_off GREAT_PRINCIPAL_8")
            return
        
        stop_name = args[0].lower()
        
        if stop_name not in self.stop_lookup:
            print(f"Unknown stop: {args[0]}")
            print("Use 'list_stops' to see all available stops")
            return
        
        division, actual_stop_name = self.stop_lookup[stop_name]
        full_id = f"{division}:{actual_stop_name}"
        
        if self.stop_router.deactivate_stop(full_id):
            stop_info = self.stops_config[division][actual_stop_name]
            print(f"OFF: {stop_info['name']} ({actual_stop_name})")
        else:
            print(f"Stop not active: {args[0]}")
    
    def cmd_key_on(self, args: list):
        """Simulate a key press."""
        if len(args) < 2:
            print("Usage: key_on MANUAL NOTE")
            print("MANUAL: G (Great), S (Swell), C (Choir), P (Pedal)")
            print("NOTE: MIDI note number (0-127)")
            return
        
        manual = args[0].upper()
        try:
            note = int(args[1])
        except ValueError:
            print(f"Invalid note number: {args[1]}")
            return
        
        if note < 0 or note > 127:
            print(f"Note must be 0-127, got {note}")
            return
        
        manual_names = {'G': 'great', 'S': 'swell', 'C': 'choir', 'P': 'pedal'}
        manual_display = {'G': 'Great', 'S': 'Swell', 'C': 'Choir', 'P': 'Pedal'}
        
        if manual not in manual_names:
            print(f"Invalid manual: {manual}. Use G, S, C, or P")
            return
        
        division = manual_names[manual]
        
        # Track key press in state
        import time
        self.active_keys[(division, note)] = time.time()
        
        # Route through stop logic
        self.stop_router.process_note_on(division, note, velocity=64)
        print(f"Key ON: {manual_display[manual]} note {note}")
    
    def cmd_key_off(self, args: list):
        """Simulate a key release."""
        if len(args) < 2:
            print("Usage: key_off MANUAL NOTE")
            return
        
        manual = args[0].upper()
        try:
            note = int(args[1])
        except ValueError:
            print(f"Invalid note number: {args[1]}")
            return
        
        manual_names = {'G': 'great', 'S': 'swell', 'C': 'choir', 'P': 'pedal'}
        manual_display = {'G': 'Great', 'S': 'Swell', 'C': 'Choir', 'P': 'Pedal'}
        
        if manual not in manual_names:
            print(f"Invalid manual: {manual}. Use G, S, C, or P")
            return
        
        division = manual_names[manual]
        
        # Track key release in state
        self.active_keys.pop((division, note), None)
        
        # Route through stop logic
        self.stop_router.process_note_off(division, note)
        print(f"Key OFF: {manual_display[manual]} note {note}")
    
    def cmd_all_clear(self):
        """Turn off all stops."""
        if self.stop_router:
            self.stop_router.clear_all_stops()
            print("All stops cleared")
        else:
            print("Stop router not initialized")
    
    def cmd_state(self, args: list):
        """Show state information."""
        import time
        
        subcommand = args[0].lower() if args else 'all'
        
        if subcommand not in ('all', 'keys', 'notes'):
            print("Usage: state [keys|notes]")
            print("  state       - Show all state (keys and notes)")
            print("  state keys  - Show only active input keys")
            print("  state notes - Show only active rank notes")
            return
        
        current_time = time.time()
        
        if subcommand in ('all', 'keys'):
            print("\n" + "="*60)
            print("ACTIVE INPUT KEYS")
            print("="*60)
            
            if not self.active_keys:
                print("  No keys pressed")
            else:
                # Group by division
                keys_by_division = {}
                for (division, note), timestamp in self.active_keys.items():
                    if division not in keys_by_division:
                        keys_by_division[division] = []
                    duration = current_time - timestamp
                    keys_by_division[division].append((note, duration))
                
                for division in sorted(keys_by_division.keys()):
                    notes = sorted(keys_by_division[division])
                    print(f"\n  {division.upper()}:")
                    for note, duration in notes:
                        print(f"    Note {note:3d} - held for {duration:6.2f}s")
        
        if subcommand in ('all', 'notes'):
            print("\n" + "="*60)
            print("ACTIVE RANK NOTES")
            print("="*60)
            
            if not self.active_rank_notes:
                print("  No rank notes playing")
            else:
                # Group by output
                notes_by_output = {}
                for (output, channel, note), (rank_id, timestamp) in self.active_rank_notes.items():
                    if output not in notes_by_output:
                        notes_by_output[output] = []
                    duration = current_time - timestamp
                    notes_by_output[output].append((channel, note, rank_id, duration))
                
                for output in sorted(notes_by_output.keys()):
                    notes = sorted(notes_by_output[output])
                    print(f"\n  {output.upper()}:")
                    for channel, note, rank_id, duration in notes:
                        print(f"    Ch{channel:2d} Note{note:3d} ({rank_id:20s}) - playing for {duration:6.2f}s")
        
        print()
    
    def cmd_status(self):
        """Show system status."""
        print("\n" + "="*60)
        print("SYSTEM STATUS")
        print("="*60)
        print(f"Running: {self.running}")
        print(f"Mode: {'Daemon' if self.daemon_mode else 'Interactive'}")
        
        active_stops = self.stop_router.get_active_stops() if self.stop_router else set()
        print(f"Active stops: {len(active_stops)}")
        
        if active_stops:
            print("\nDrawn stops:")
            for stop_id in sorted(active_stops):
                division, stop_name = stop_id.split(':', 1)
                stop_info = self.stops_config[division][stop_name]
                print(f"  - {stop_info['name']} ({stop_id})")
        
        print(f"\nMIDI outputs: {len(self.midi_outputs)}")
        for name in self.midi_outputs.keys():
            print(f"  - {name}")
        print()
    
    def cmd_list_stops(self, args: list):
        """List available stops."""
        division_filter = args[0].lower() if args else None
        
        if division_filter and division_filter not in self.stops_config:
            print(f"Unknown division: {division_filter}")
            print(f"Available divisions: {', '.join(self.stops_config.keys())}")
            return
        
        divisions = [division_filter] if division_filter else self.stops_config.keys()
        
        print("\n" + "="*60)
        print("AVAILABLE STOPS")
        print("="*60)
        
        active_stops = self.stop_router.get_active_stops() if self.stop_router else set()
        
        for division in sorted(divisions):
            stops = self.stops_config.get(division, {})
            print(f"\n{division.upper()} ({len(stops)} stops):")
            for stop_id, stop_info in stops.items():
                active = "✓" if f"{division}:{stop_id}" in active_stops else " "
                print(f"  [{active}] {stop_id:30} - {stop_info['name']}")
        print()
    
    def stop(self):
        """Stop the organ controller service."""
        if self._shutdown_requested and not self.running:
            return  # Already stopped
        
        logger.info("=== Organ Controller Stopping ===")
        self.running = False
        
        if self.midi_input:
            self.midi_input.stop()
        
        for name, output in self.midi_outputs.items():
            if output:
                logger.info(f"Stopping output '{name}'")
                output.stop()
        
        self.midi_outputs.clear()
        logger.info("=== Organ Controller Stopped ===")


def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Organ Controller Service')
    parser.add_argument('--daemon', action='store_true', 
                        help='Run in daemon mode (no interactive console)')
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=logging.DEBUG)
    
    # Create and start controller
    controller = OrganController(daemon_mode=args.daemon)
    
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

