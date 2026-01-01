"""Input mapper that routes incoming MIDI messages to the correct handlers.

Maps MIDI channels and note ranges to organ divisions, stops, etc.
"""

import logging
from typing import Dict, Optional, Callable
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class InputMapper:
    """Maps MIDI input messages to organ control functions."""
    
    def __init__(self, config_path: str, stop_router, stops_config: dict, controller=None):
        """Initialize the input mapper.
        
        Args:
            config_path: Path to input_map.yaml configuration file
            stop_router: StopRouter instance for routing notes
            stops_config: Stops configuration dictionary
            controller: OrganController instance for state tracking (optional)
        """
        self.stop_router = stop_router
        self.stops_config = stops_config
        self.controller = controller
        self.config = self._load_config(config_path)
        
        # Build quick lookup dictionaries
        self.manual_channels = {}  # channel -> division name
        self.manual_ranges = {}    # channel -> (first_key, last_key)
        self.pedal_channel = None
        self.pedal_range = None
        self.stop_channel = None
        self.stop_mappings = {}    # note -> (division, stop_id)
        
        self._build_lookups()
        
    def _load_config(self, config_path: str) -> dict:
        """Load input mapping configuration from YAML file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config_file = Path(config_path)
        logger.info(f"Loading input map configuration from: {config_file}")
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Input map configuration loaded successfully")
            return config
        except Exception as e:
            logger.error(f"Failed to load input map configuration: {e}")
            raise
    
    def _build_lookups(self):
        """Build quick lookup dictionaries from configuration."""
        # Manual keyboards
        manuals = self.config.get('manuals', {})
        for division, manual_config in manuals.items():
            channel = manual_config['channel']
            keys = manual_config['keys']
            self.manual_channels[channel] = division
            self.manual_ranges[channel] = (keys['first_note'], keys['last_note'])
        
        logger.info(f"Manual channels: {self.manual_channels}")
        
        # Pedal board
        pedal = self.config.get('pedal', {})
        if pedal:
            self.pedal_channel = pedal['channel']
            keys = pedal['keys']
            self.pedal_range = (keys['first_note'], keys['last_note'])
            logger.info(f"Pedal channel: {self.pedal_channel}, range: {self.pedal_range}")
        
        # Stop board
        stops = self.config.get('stops', {})
        if stops:
            self.stop_channel = stops['channel']
            mappings = stops.get('mappings', {})
            for note, stop_spec in mappings.items():
                # Parse format: "division:STOP_ID"
                if ':' in stop_spec:
                    division, stop_id = stop_spec.split(':', 1)
                    self.stop_mappings[int(note)] = (division, stop_id)
            logger.info(f"Stop channel: {self.stop_channel}, {len(self.stop_mappings)} stops mapped")
    
    def process_message(self, msg):
        """Process an incoming MIDI message and route it appropriately.
        
        Args:
            msg: mido.Message object
        """
        if msg.type not in ('note_on', 'note_off'):
            # For now, ignore non-note messages
            logger.debug(f"Ignoring message type: {msg.type}")
            return
        
        channel = msg.channel
        note = msg.note
        velocity = msg.velocity
        
        # Check if this is a manual keyboard
        if channel in self.manual_channels:
            division = self.manual_channels[channel]
            first_key, last_key = self.manual_ranges[channel]
            
            # Check if note is in key range (not piston)
            if first_key <= note <= last_key:
                self._handle_key_event(division, note, velocity, msg.type)
            else:
                # Piston - ignore for now
                logger.debug(f"Ignoring piston on {division}: note {note}")
            return
        
        # Check if this is pedal
        if channel == self.pedal_channel:
            first_key, last_key = self.pedal_range
            if first_key <= note <= last_key:
                self._handle_key_event('pedal', note, velocity, msg.type)
            else:
                # Pedal piston - ignore for now
                logger.debug(f"Ignoring pedal piston: note {note}")
            return
        
        # Check if this is stop board
        if channel == self.stop_channel:
            if note in self.stop_mappings:
                self._handle_stop_event(note, msg.type)
            else:
                logger.debug(f"Unmapped stop note: {note}")
            return
        
        # Unknown channel
        logger.debug(f"Unknown MIDI channel: {channel}")
    
    def _handle_key_event(self, division: str, note: int, velocity: int, msg_type: str):
        """Handle a key press/release event.
        
        Args:
            division: Division name (great, swell, choir, pedal)
            note: MIDI note number
            velocity: MIDI velocity
            msg_type: 'note_on' or 'note_off'
        """
        import time
        
        if msg_type == 'note_on' and velocity > 0:
            logger.info(f"Key ON: {division.upper()} note {note} vel {velocity}")
            # Track key press
            if self.controller:
                self.controller.active_keys[(division, note)] = time.time()
            self.stop_router.process_note_on(division, note, velocity)
        else:
            logger.info(f"Key OFF: {division.upper()} note {note}")
            # Track key release
            if self.controller:
                self.controller.active_keys.pop((division, note), None)
            self.stop_router.process_note_off(division, note)
    
    def _handle_stop_event(self, note: int, msg_type: str):
        """Handle a stop draw/cancel event.
        
        Args:
            note: MIDI note number representing the stop
            msg_type: 'note_on' or 'note_off'
        """
        division, stop_id = self.stop_mappings[note]
        
        if msg_type == 'note_on':
            logger.info(f"STOP DRAW: {division.upper()}:{stop_id}")
            self.stop_router.activate_stop(f"{division}:{stop_id}")
        else:
            logger.info(f"STOP CANCEL: {division.upper()}:{stop_id}")
            self.stop_router.deactivate_stop(f"{division}:{stop_id}")
