"""Stop logic module.

Handles routing of notes through drawn stops to physical/virtual ranks.
"""

import logging
from typing import Dict, List, Set, Tuple, Optional
import mido

logger = logging.getLogger('organcontroller.stops')


class StopRouter:
    """Routes notes through drawn stops to the appropriate ranks."""
    
    def __init__(self, stops_config: dict, ranks_config: dict, midi_outputs: dict, controller=None, port_to_output_map: dict = None):
        """Initialize the stop router.
        
        Args:
            stops_config: Stops configuration (from stops.yaml)
            ranks_config: Ranks configuration (from ranks.yaml)
            midi_outputs: Dictionary of MIDI output objects by name
            controller: OrganController instance for state tracking (optional)
            port_to_output_map: Mapping from 'client:port' to output name (optional)
        """
        self.stops_config = stops_config
        self.ranks_config = ranks_config
        self.midi_outputs = midi_outputs
        self.controller = controller
        self.port_to_output_map = port_to_output_map or {}
        self.active_stops: Set[str] = set()
        
        # Build a lookup for ranks by ID
        self.ranks = {}
        for rank_id, rank_info in ranks_config.get('physical_ranks', {}).items():
            self.ranks[rank_id] = rank_info
        for rank_id, rank_info in ranks_config.get('virtual_ranks', {}).items():
            self.ranks[rank_id] = rank_info
        
        logger.info(f"StopRouter initialized with {len(self.ranks)} ranks")
    
    def get_active_stops(self) -> Set[str]:
        """Get the set of active stop IDs."""
        return self.active_stops.copy()
    
    def activate_stop(self, stop_id: str) -> bool:
        """Activate a stop.
        
        Args:
            stop_id: Stop ID (e.g., "GREAT_PRINCIPAL_8")
        
        Returns:
            True if stop was activated, False if invalid
        """
        # Look up which division this stop belongs to
        division = None
        stop_name = stop_id
        
        for div in ['great', 'swell', 'choir', 'pedal']:
            if div in self.stops_config and stop_id in self.stops_config[div]:
                division = div
                break
        
        if not division:
            logger.warning(f"Stop not found: {stop_id}")
            return False
        
        # Create internal ID with division prefix for tracking
        internal_id = f"{division}:{stop_name}"
        
        # Check if stop was already active
        was_active = internal_id in self.active_stops
        
        self.active_stops.add(internal_id)
        logger.info(f"Stop activated: {stop_id}")
        
        # If stop was just activated and we have controller state, sound any held keys
        if not was_active and self.controller and hasattr(self.controller, 'active_keys'):
            # Find all held keys for this division
            held_keys = [(div, note) for (div, note) in self.controller.active_keys.keys() 
                        if div == division]
            
            if held_keys:
                logger.debug(f"Sounding {len(held_keys)} held keys on newly activated stop {stop_id}")
                for _, note in held_keys:
                    # Get velocity from original key press if available, otherwise use default
                    velocity = 64
                    # Route this note through the newly activated stop
                    self._route_note_through_stop(internal_id, note, velocity, True)
        
        return True
    
    def deactivate_stop(self, stop_id: str) -> bool:
        """Deactivate a stop.
        
        Args:
            stop_id: Stop ID (e.g., "GREAT_PRINCIPAL_8")
        
        Returns:
            True if stop was deactivated, False if not active
        """
        # Look up which division this stop belongs to
        division = None
        
        for div in ['great', 'swell', 'choir', 'pedal']:
            if div in self.stops_config and stop_id in self.stops_config[div]:
                division = div
                break
        
        if not division:
            logger.warning(f"Stop not found: {stop_id}")
            return False
        
        # Create internal ID with division prefix
        internal_id = f"{division}:{stop_id}"
        
        if internal_id in self.active_stops:
            # Before removing, silence any held keys on this stop
            if self.controller and hasattr(self.controller, 'active_keys'):
                held_keys = [(div, note) for (div, note) in self.controller.active_keys.keys() 
                            if div == division]
                
                if held_keys:
                    logger.debug(f"Silencing {len(held_keys)} held keys on deactivated stop {stop_id}")
                    for _, note in held_keys:
                        # Send note_off for this stop
                        self._route_note_through_stop(internal_id, note, 0, False)
            
            self.active_stops.remove(internal_id)
            logger.info(f"Stop deactivated: {stop_id}")
            return True
        return False
    
    def clear_all_stops(self):
        """Deactivate all stops."""
        count = len(self.active_stops)
        self.active_stops.clear()
        logger.info(f"All stops cleared ({count} were active)")
    
    def _route_note_through_stop(self, stop_id: str, note: int, velocity: int, is_note_on: bool):
        """Route a single note through a specific stop to its ranks.
        
        Args:
            stop_id: Stop ID in format "division:STOP_NAME"
            note: MIDI note number
            velocity: MIDI velocity
            is_note_on: True for note_on, False for note_off
        """
        division, stop_name = stop_id.split(':', 1)
        division = division.lower()
        
        stop_info = self.stops_config[division][stop_name]
        
        # Track which rank/note combinations we've sent to avoid duplicates
        sent_notes: Set[Tuple[str, int]] = set()
        
        # Process each rank in the stop
        for rank_config in stop_info.get('ranks', []):
            rank_id = rank_config['rank']
            rank_transpose = rank_config.get('transpose', 0)
            
            # Calculate the target note for this stop
            target_pitch = note + rank_transpose
            
            # Get rank info
            rank_info = self.ranks.get(rank_id)
            if not rank_info:
                logger.warning(f"Unknown rank: {rank_id}")
                continue
            
            c4_pitch_note = rank_info.get('c4_pitch_note')
            if c4_pitch_note is None:
                logger.warning(f"Rank {rank_id} has no c4_pitch_note")
                continue
            
            # Calculate the actual note to send to the rank
            rank_note = target_pitch + (c4_pitch_note - 60)
            
            # Check if the note is within the rank's range
            first_note = rank_info.get('first_note')
            last_note = rank_info.get('last_note')
            
            if first_note is not None and rank_note < first_note:
                continue
            
            if last_note is not None and rank_note > last_note:
                continue
            
            # Avoid sending duplicate notes to the same rank
            note_key = (rank_id, rank_note)
            if note_key in sent_notes:
                continue
            sent_notes.add(note_key)
            
            # Send the note to the appropriate output
            self._send_to_rank(rank_id, rank_info, rank_config, rank_note, velocity, is_note_on)
    
    def process_note_on(self, division: str, note: int, velocity: int = 64):
        """Process a note-on event for a given manual/pedal division.
        
        Args:
            division: Division name ('great', 'swell', 'choir', 'pedal')
            note: MIDI note number (0-127)
            velocity: MIDI velocity (0-127)
        """
        division = division.lower()
        
        # Find all active stops for this division
        active_division_stops = [
            stop_id for stop_id in self.active_stops 
            if stop_id.startswith(f"{division}:")
        ]
        
        if not active_division_stops:
            logger.debug(f"No stops drawn on {division}, note {note} ignored")
            return
        
        logger.debug(f"Processing note_on: {division} note {note}, {len(active_division_stops)} stops active")
        
        # Track which rank/note combinations we've already sent to avoid duplicates
        sent_notes: Set[Tuple[str, int]] = set()
        
        # Route through each active stop
        for stop_id in active_division_stops:
            _, stop_name = stop_id.split(':', 1)
            stop_info = self.stops_config[division][stop_name]
            
            # Process each rank in the stop
            for rank_config in stop_info.get('ranks', []):
                rank_id = rank_config['rank']
                rank_transpose = rank_config.get('transpose', 0)
                
                # Calculate the target note for this stop
                # played_note + stop_transpose gives us the desired pitch
                target_pitch = note + rank_transpose
                
                # Now convert to the rank's native note space
                # The rank expects notes based on its c4_pitch_note
                rank_info = self.ranks.get(rank_id)
                if not rank_info:
                    logger.warning(f"Unknown rank: {rank_id}")
                    continue
                
                c4_pitch_note = rank_info.get('c4_pitch_note')
                if c4_pitch_note is None:
                    logger.warning(f"Rank {rank_id} has no c4_pitch_note")
                    continue
                
                # Calculate the actual note to send to the rank
                # target_pitch is what we want to sound (in 8' reference)
                # We need to adjust for the rank's actual pitch
                rank_note = target_pitch + (c4_pitch_note - 60)
                
                # Check if the note is within the rank's range
                first_note = rank_info.get('first_note')
                last_note = rank_info.get('last_note')
                
                if first_note is not None and rank_note < first_note:
                    logger.debug(f"Note {rank_note} below rank {rank_id} range (first={first_note})")
                    continue
                
                if last_note is not None and rank_note > last_note:
                    logger.debug(f"Note {rank_note} above rank {rank_id} range (last={last_note})")
                    continue
                
                # Avoid sending duplicate notes to the same rank
                note_key = (rank_id, rank_note)
                if note_key in sent_notes:
                    logger.debug(f"Skipping duplicate: rank {rank_id} note {rank_note}")
                    continue
                sent_notes.add(note_key)
                
                # Send the note to the appropriate output
                self._send_to_rank(rank_id, rank_info, rank_config, rank_note, velocity, True)
    
    def process_note_off(self, division: str, note: int):
        """Process a note-off event for a given manual/pedal division.
        
        Args:
            division: Division name ('great', 'swell', 'choir', 'pedal')
            note: MIDI note number (0-127)
        """
        division = division.lower()
        
        # Find all active stops for this division
        active_division_stops = [
            stop_id for stop_id in self.active_stops 
            if stop_id.startswith(f"{division}:")
        ]
        
        if not active_division_stops:
            return
        
        logger.debug(f"Processing note_off: {division} note {note}")
        
        # Track which rank/note combinations we've sent
        sent_notes: Set[Tuple[str, int]] = set()
        
        # Route through each active stop (same logic as note_on)
        for stop_id in active_division_stops:
            _, stop_name = stop_id.split(':', 1)
            stop_info = self.stops_config[division][stop_name]
            
            for rank_config in stop_info.get('ranks', []):
                rank_id = rank_config['rank']
                rank_transpose = rank_config.get('transpose', 0)
                
                target_pitch = note + rank_transpose
                
                rank_info = self.ranks.get(rank_id)
                if not rank_info:
                    continue
                
                c4_pitch_note = rank_info.get('c4_pitch_note')
                if c4_pitch_note is None:
                    continue
                
                rank_note = target_pitch + (c4_pitch_note - 60)
                
                # Check range
                first_note = rank_info.get('first_note')
                last_note = rank_info.get('last_note')
                
                if first_note is not None and rank_note < first_note:
                    continue
                if last_note is not None and rank_note > last_note:
                    continue
                
                # Avoid duplicates
                note_key = (rank_id, rank_note)
                if note_key in sent_notes:
                    continue
                sent_notes.add(note_key)
                
                # Send note off
                self._send_to_rank(rank_id, rank_info, rank_config, rank_note, 0, False)
    
    def _send_to_rank(self, rank_id: str, rank_info: dict, rank_config: dict, note: int, velocity: int, is_note_on: bool):
        """Send a MIDI message to a specific rank.
        
        Args:
            rank_id: Rank identifier
            rank_info: Rank information from ranks config
            rank_config: Rank configuration from stop (includes velocity_min/max, transpose)
            note: MIDI note number
            velocity: Original MIDI velocity (will be scaled/clamped for note_on)
            is_note_on: True for note_on, False for note_off
        """
        # Apply velocity scaling/clamping if this is a note_on
        if is_note_on:
            velocity_min = rank_config.get('velocity_min', 1)
            velocity_max = rank_config.get('velocity_max', 127)
            
            # Clamp to the specified range
            velocity = max(velocity_min, min(velocity_max, velocity))
            
            if velocity_min == velocity_max:
                # Fixed velocity mode - ignore input velocity
                logger.debug(f"Using fixed velocity {velocity} for {rank_id}")
            else:
                # TODO: Could add velocity scaling here if velocity_min != 1 or velocity_max != 127
                logger.debug(f"Velocity clamped to range [{velocity_min}, {velocity_max}] -> {velocity}")
        
        midi_address = rank_info.get('midi_address', '')
        
        # Parse MIDI address to determine output and channel
        # Format: "device_name:port_name client:port:channel"
        # Examples:
        #   "U6MIDI Pro:U6MIDI Pro MIDI 3 20:2:0"
        #   "FS_Virtual:FS_Virtual 128:0:5"
        
        if not midi_address:
            logger.warning(f"No MIDI address for rank {rank_id}")
            return
        
        parts = midi_address.split()
        if len(parts) < 2:
            logger.warning(f"Invalid MIDI address format for rank {rank_id}: {midi_address}")
            return
        
        # Last part has format "client:port:channel"
        addr_parts = parts[-1].split(':')
        if len(addr_parts) < 3:
            logger.warning(f"Invalid MIDI address format for rank {rank_id}: {midi_address}")
            return
        
        # Extract channel and client:port
        try:
            channel = int(addr_parts[-1])
            client_port = ':'.join(addr_parts[:-1])  # "client:port"
        except ValueError:
            logger.warning(f"Invalid channel in MIDI address for rank {rank_id}: {midi_address}")
            return
        
        # Look up output name from config-driven map
        output_name = self.port_to_output_map.get(client_port)
        if not output_name or output_name not in self.midi_outputs:
            logger.warning(f"No output found for rank {rank_id} (client:port: {client_port})")
            return
        
        output = self.midi_outputs[output_name]
        
        # Create and send MIDI message
        msg_type = 'note_on' if is_note_on else 'note_off'
        msg = mido.Message(msg_type, note=note, velocity=velocity, channel=channel)
        
        try:
            output.send_message(msg)
            logger.debug(f"Sent {msg_type} to {rank_id} ({output_name}): note={note} vel={velocity} ch={channel}")
            
            # Track rank notes in controller state
            if self.controller:
                import time
                note_key = (output_name, channel, note)
                if is_note_on:
                    self.controller.active_rank_notes[note_key] = (rank_id, time.time())
                else:
                    self.controller.active_rank_notes.pop(note_key, None)
        except Exception as e:
            logger.error(f"Failed to send to rank {rank_id}: {e}")
