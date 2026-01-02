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
from master.web_api import OrganWebAPI
from master.actions import Actions

logger = get_logger('main')


class OrganController:
    """Main organ controller service."""
    
    def __init__(self, config_dir: str = "config/hybrid_organ", 
                 daemon_mode: bool = False):
        """Initialize the organ controller.
        
        Args:
            config_dir: Directory containing configuration files (midi_ports.yaml, ranks.yaml, stops.yaml, input_map.yaml)
            daemon_mode: If True, run as daemon; if False, run interactive mode
        """
        self.config_dir = config_dir
        self.config_path = f"{config_dir}/midi_ports.yaml"
        self.ranks_config_path = f"{config_dir}/ranks.yaml"
        self.stops_config_path = f"{config_dir}/stops.yaml"
        self.input_map_config_path = f"{config_dir}/input_map.yaml"
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
        self.web_api: OrganWebAPI = None  # Web API server
        self.actions: Actions = None  # Unified actions for CLI and API
        
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
    def _build_port_to_output_map(self, config: dict) -> dict:
        """Build a mapping from 'client:port' to output name.
        
        Args:
            config: MIDI ports configuration
            
        Returns:
            Dictionary mapping 'client:port' string to output name
        """
        port_map = {}
        for output_name, port_address in config.get('output_ports', {}).items():
            # Extract client:port from address like "FS_Virtual:FS_Virtual 128:0"
            # Format is "device_name:port_name client:port"
            parts = port_address.split()
            if len(parts) >= 2:
                client_port = parts[-1]  # Last part is "client:port"
                port_map[client_port] = output_name
        return port_map    
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
            Stops configuration dictionary with division metadata added
        """
        stops_file = Path(__file__).parent.parent.parent / self.stops_config_path
        logger.info(f"Loading stops configuration from: {stops_file}")
        
        try:
            with open(stops_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Add division metadata to each stop for easy lookup
            for division, stops in config.items():
                for stop_id, stop_data in stops.items():
                    stop_data['division'] = division
            
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
        config = self.load_config()
        port_to_output = self._build_port_to_output_map(config)
        self.stop_router = StopRouter(self.stops_config, self.ranks_config, self.midi_outputs, self, port_to_output)
        logger.info("Stop router initialized")
        
        # Build flat stop lookup map: stop_id -> stop_data (with division embedded)
        self.stop_index = {}  # stop_id -> stop_data
        for division in ['great', 'swell', 'choir', 'pedal']:
            if division in self.stops_config:
                for stop_id, stop_data in self.stops_config[division].items():
                    self.stop_index[stop_id] = stop_data
        logger.info(f"Stop index built: {len(self.stop_index)} stops")
        
        # Initialize input mapper
        input_map_path = Path(__file__).parent.parent.parent / self.input_map_config_path
        self.input_mapper = InputMapper(str(input_map_path), self.stop_router, self.stops_config, self)
        logger.info("Input mapper initialized")
        
        # Initialize MIDI input with callback
        self.midi_input = MidiInput(input_port, self.on_midi_message)
        self.midi_input.start()
        
        # Start web API
        self.web_api = OrganWebAPI(self, host='0.0.0.0', port=5000)
        self.web_api.start()
        
        # Initialize unified actions for CLI and API
        self.actions = Actions(self)
        
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
        elif cmd == "panic":
            self.cmd_panic()
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
  panic                     - Send MIDI panic (all notes off) to all outputs
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
        
        result = self.actions.activate_stop(args[0])
        if result['success']:
            print(f"ON: {result['stop_name']} ({result['stop_id']})")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    def cmd_stop_off(self, args: list):
        """Turn off a stop."""
        if not args:
            print("Usage: stop_off STOP_NAME")
            print("Example: stop_off great_principal_8 or stop_off GREAT_PRINCIPAL_8")
            return
        
        result = self.actions.deactivate_stop(args[0])
        if result['success']:
            print(f"OFF: {result['stop_name']} ({result['stop_id']})")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
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
        
        result = self.actions.simulate_key_on(manual, note)
        if result['success']:
            manual_display = {'G': 'Great', 'S': 'Swell', 'C': 'Choir', 'P': 'Pedal'}
            print(f"Key ON: {manual_display[manual]} note {note}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
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
        
        result = self.actions.simulate_key_off(manual, note)
        if result['success']:
            manual_display = {'G': 'Great', 'S': 'Swell', 'C': 'Choir', 'P': 'Pedal'}
            print(f"Key OFF: {manual_display[manual]} note {note}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    def cmd_all_clear(self):
        """Turn off all stops."""
        result = self.actions.all_clear()
        if result['success']:
            print(f"All stops cleared ({result['count']} stops)")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    def cmd_panic(self):
        """Send MIDI panic to all outputs."""
        result = self.actions.panic()
        if result['success']:
            print(f"MIDI panic sent to {result['outputs_count']} outputs")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    def cmd_state(self, args: list):
        """Show state information."""
        subcommand = args[0].lower() if args else 'all'
        
        if subcommand not in ('all', 'keys', 'notes'):
            print("Usage: state [keys|notes]")
            print("  state       - Show all state (keys and notes)")
            print("  state keys  - Show only active input keys")
            print("  state notes - Show only active rank notes")
            return
        
        state_type = None if subcommand == 'all' else subcommand
        result = self.actions.get_state(state_type)
        
        if not result['success']:
            print(f"Error: {result.get('error', 'Unknown error')}")
            return
        
        import time
        current_time = time.time()
        
        if 'keys' in result:
            print("\n" + "="*60)
            print("ACTIVE INPUT KEYS")
            print("="*60)
            
            if not result['keys']:
                print("  No keys pressed")
            else:
                # Group by division
                keys_by_division = {}
                for key in result['keys']:
                    division = key['division']
                    note = key['note']
                    timestamp = key['timestamp']
                    if division not in keys_by_division:
                        keys_by_division[division] = []
                    duration = current_time - timestamp
                    keys_by_division[division].append((note, duration))
                
                for division in sorted(keys_by_division.keys()):
                    notes = sorted(keys_by_division[division])
                    print(f"\n  {division.upper()}:")
                    for note, duration in notes:
                        print(f"    Note {note:3d} - held for {duration:6.2f}s")
        
        if 'notes' in result:
            print("\n" + "="*60)
            print("ACTIVE RANK NOTES")
            print("="*60)
            
            if not result['notes']:
                print("  No rank notes playing")
            else:
                # Group by rank
                notes_by_rank = {}
                for note_data in result['notes']:
                    rank = note_data['rank']
                    note = note_data['note']
                    timestamp = note_data['timestamp']
                    if rank not in notes_by_rank:
                        notes_by_rank[rank] = []
                    duration = current_time - timestamp
                    notes_by_rank[rank].append((note, duration))
                
                for rank in sorted(notes_by_rank.keys()):
                    notes = sorted(notes_by_rank[rank])
                    print(f"\n  {rank}:")
                    for note, duration in notes:
                        print(f"    Note {note:3d} - playing for {duration:6.2f}s")
        
        print("")
    
    def cmd_status(self):
        """Show system status."""
        result = self.actions.get_status()
        
        print("\n" + "="*60)
        print("SYSTEM STATUS")
        print("="*60)
        print(f"Running: {self.running}")
        print(f"Mode: {'Daemon' if self.daemon_mode else 'Interactive'}")
        
        if result['success']:
            print(f"Active stops: {len(result['active_stops'])}")
            
            if result['active_stops']:
                print("\nDrawn stops:")
                for stop in sorted(result['active_stops'], key=lambda s: (s['division'], s['id'])):
                    print(f"  - {stop['name']} ({stop['id']})")
            
            print(f"\nActive keys: {result['active_keys']}")
            print(f"Active rank notes: {result['active_notes']}")
        else:
            print(f"Error getting status: {result.get('error', 'Unknown error')}")
        
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
        
        result = self.actions.list_stops(division_filter)
        
        if not result['success']:
            print(f"Error: {result.get('error', 'Unknown error')}")
            return
        
        print("\n" + "="*60)
        print("AVAILABLE STOPS")
        print("="*60)
        
        # Group by division
        stops_by_division = {}
        for stop in result['stops']:
            div = stop['division']
            if div not in stops_by_division:
                stops_by_division[div] = []
            stops_by_division[div].append(stop)
        
        for division in sorted(stops_by_division.keys()):
            stops = stops_by_division[division]
            print(f"\n{division.upper()} ({len(stops)} stops):")
            for stop in stops:
                active = "✓" if stop['active'] else " "
                print(f"  [{active}] {stop['id']:30} - {stop['name']}")
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
    parser.add_argument('--config', type=str, default='config/hybrid_organ',
                        help='Configuration directory (default: config/hybrid_organ)')
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=logging.DEBUG)
    
    logger.info(f"Using configuration directory: {args.config}")
    
    # Create controller
    controller = OrganController(config_dir=args.config, daemon_mode=args.daemon)
    
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

