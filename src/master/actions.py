"""
Unified actions for organ controller.

This module provides a single implementation of all control actions
that can be used by both the interactive command-line interface
and the web API.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class Actions:
    """Unified actions for organ control."""
    
    def __init__(self, controller):
        """Initialize actions with controller reference.
        
        Args:
            controller: OrganController instance
        """
        self.controller = controller
    
    def activate_stop(self, stop_id: str) -> Dict[str, Any]:
        """Activate a stop.
        
        Args:
            stop_id: Stop ID (case-insensitive, e.g., "GREAT_PRINCIPAL_8" or "great_principal_8")
        
        Returns:
            dict with 'success' (bool), 'stop_id' (str), 'stop_name' (str), 
            and optional 'error' (str)
        """
        try:
            # Case-insensitive lookup
            original_id = stop_id
            stop_id_upper = stop_id.upper()
            
            # Try to find stop in index (case-insensitive)
            stop_data = self.controller.stop_index.get(stop_id_upper)
            if not stop_data:
                # Try case-insensitive search
                for sid, sdata in self.controller.stop_index.items():
                    if sid.upper() == stop_id_upper:
                        stop_id_upper = sid
                        stop_data = sdata
                        break
            
            if not stop_data:
                return {
                    'success': False,
                    'error': f'Unknown stop: {original_id}'
                }
            
            if not self.controller.stop_router:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
            
            if self.controller.stop_router.activate_stop(stop_id_upper):
                return {
                    'success': True,
                    'stop_id': stop_id_upper,
                    'stop_name': stop_data.get('name', stop_id_upper)
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to activate stop'
                }
        except Exception as e:
            logger.error(f"Error activating stop {stop_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def deactivate_stop(self, stop_id: str) -> Dict[str, Any]:
        """Deactivate a stop.
        
        Args:
            stop_id: Stop ID (case-insensitive, e.g., "GREAT_PRINCIPAL_8" or "great_principal_8")
        
        Returns:
            dict with 'success' (bool), 'stop_id' (str), 'stop_name' (str),
            and optional 'error' (str)
        """
        try:
            # Case-insensitive lookup
            original_id = stop_id
            stop_id_upper = stop_id.upper()
            
            # Try to find stop in index (case-insensitive)
            stop_data = self.controller.stop_index.get(stop_id_upper)
            if not stop_data:
                # Try case-insensitive search
                for sid, sdata in self.controller.stop_index.items():
                    if sid.upper() == stop_id_upper:
                        stop_id_upper = sid
                        stop_data = sdata
                        break
            
            if not stop_data:
                return {
                    'success': False,
                    'error': f'Unknown stop: {original_id}'
                }
            
            if not self.controller.stop_router:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
            
            if self.controller.stop_router.deactivate_stop(stop_id_upper):
                return {
                    'success': True,
                    'stop_id': stop_id_upper,
                    'stop_name': stop_data.get('name', stop_id_upper)
                }
            else:
                return {
                    'success': False,
                    'error': 'Stop not active'
                }
        except Exception as e:
            logger.error(f"Error deactivating stop {stop_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def all_clear(self) -> Dict[str, Any]:
        """Deactivate all stops.
        
        Returns:
            dict with 'success' (bool), 'count' (int), and optional 'error' (str)
        """
        try:
            if not self.controller.stop_router:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
            
            # Get list of active stops before clearing
            active_stops = list(self.controller.stop_router.active_stops)
            count = len(active_stops)
            
            # Deactivate each stop properly so note_off messages are sent
            for internal_id in active_stops:
                if ':' in internal_id:
                    _, stop_id = internal_id.split(':', 1)
                    self.controller.stop_router.deactivate_stop(stop_id)
            
            return {
                'success': True,
                'count': count
            }
        except Exception as e:
            logger.error(f"Error clearing stops: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def panic(self) -> Dict[str, Any]:
        """Send all-notes-off and all-sound-off to all MIDI outputs.
        
        Returns:
            dict with 'success' (bool), 'outputs_count' (int), and optional 'error' (str)
        """
        try:
            import mido
            
            outputs_count = len(self.controller.midi_outputs)
            
            # Send panic messages to all outputs on all channels
            for output_name, output in self.controller.midi_outputs.items():
                logger.info(f"Sending panic to {output_name}")
                for channel in range(16):  # MIDI has 16 channels (0-15)
                    try:
                        # All Notes Off (CC 123)
                        output.send_message(mido.Message('control_change', 
                                                        control=123, value=0, channel=channel))
                        # All Sound Off (CC 120)
                        output.send_message(mido.Message('control_change', 
                                                        control=120, value=0, channel=channel))
                        # Reset All Controllers (CC 121)
                        output.send_message(mido.Message('control_change', 
                                                        control=121, value=0, channel=channel))
                    except Exception as e:
                        logger.warning(f"Error sending panic to {output_name} channel {channel}: {e}")
            
            # Clear internal state
            self.controller.active_keys.clear()
            self.controller.active_rank_notes.clear()
            
            logger.info(f"Panic sent to {outputs_count} MIDI outputs")
            return {
                'success': True,
                'outputs_count': outputs_count
            }
        except Exception as e:
            logger.error(f"Error during panic: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_stops(self, division: Optional[str] = None) -> Dict[str, Any]:
        """List all stops, optionally filtered by division.
        
        Args:
            division: Optional division to filter by (e.g., "great", "swell")
        
        Returns:
            dict with 'success' (bool), 'stops' (list of dicts), and optional 'error' (str)
        """
        try:
            stops = []
            
            if division:
                division = division.lower()
                if division not in self.controller.stops_config:
                    return {
                        'success': False,
                        'error': f'Unknown division: {division}'
                    }
                divisions_to_list = [division]
            else:
                divisions_to_list = ['great', 'swell', 'choir', 'pedal']
            
            for div in divisions_to_list:
                if div not in self.controller.stops_config:
                    continue
                
                for stop_id, stop_data in self.controller.stops_config[div].items():
                    # Check if stop is currently active
                    is_active = False
                    if self.controller.stop_router:
                        internal_id = f"{div}:{stop_id}"
                        is_active = internal_id in self.controller.stop_router.active_stops
                    
                    stops.append({
                        'id': stop_id,
                        'name': stop_data.get('name', stop_id),
                        'division': div,
                        'active': is_active
                    })
            
            return {
                'success': True,
                'stops': stops
            }
        except Exception as e:
            logger.error(f"Error listing stops: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_active_stops(self) -> Dict[str, Any]:
        """Get list of currently active stops.
        
        Returns:
            dict with 'success' (bool), 'stops' (list of stop_ids), and optional 'error' (str)
        """
        try:
            if not self.controller.stop_router:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
            
            # Extract stop IDs from internal "division:STOP_ID" format
            active_stops = []
            for internal_id in self.controller.stop_router.active_stops:
                if ':' in internal_id:
                    _, stop_id = internal_id.split(':', 1)
                    active_stops.append(stop_id)
            
            return {
                'success': True,
                'stops': active_stops
            }
        except Exception as e:
            logger.error(f"Error getting active stops: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get system status.
        
        Returns:
            dict with 'success' (bool), 'active_stops' (list), 'active_keys' (int),
            'active_notes' (int), and optional 'error' (str)
        """
        try:
            # Get active stops (extract from internal format)
            active_stops = []
            if self.controller.stop_router:
                for internal_id in self.controller.stop_router.active_stops:
                    if ':' in internal_id:
                        _, stop_id = internal_id.split(':', 1)
                        stop_data = self.controller.stop_index.get(stop_id)
                        if stop_data:
                            active_stops.append({
                                'id': stop_id,
                                'name': stop_data.get('name', stop_id),
                                'division': stop_data.get('division', 'unknown')
                            })
            
            return {
                'success': True,
                'active_stops': active_stops,
                'active_keys': len(self.controller.active_keys),
                'active_notes': len(self.controller.active_rank_notes)
            }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_state(self, state_type: Optional[str] = None) -> Dict[str, Any]:
        """Get current state (keys, notes, or both).
        
        Args:
            state_type: Optional filter - 'keys', 'notes', or None for both
        
        Returns:
            dict with 'success' (bool), and 'keys'/'notes'/'active_stops' data, and optional 'error' (str)
        """
        try:
            result = {'success': True}
            
            if state_type is None or state_type == 'keys':
                # Format active keys
                keys = []
                for (division, note), timestamp in self.controller.active_keys.items():
                    keys.append({
                        'division': division,
                        'note': note,
                        'timestamp': timestamp
                    })
                result['keys'] = keys
            
            if state_type is None or state_type == 'notes':
                # Format active rank notes
                notes = []
                for (output, channel, note), (rank_id, timestamp) in self.controller.active_rank_notes.items():
                    notes.append({
                        'rank': rank_id,
                        'output': output,
                        'channel': channel,
                        'note': note,
                        'timestamp': timestamp
                    })
                result['notes'] = notes
            
            # Always include active stops (extract from internal format)
            active_stops = []
            if self.controller.stop_router:
                for internal_id in self.controller.stop_router.active_stops:
                    if ':' in internal_id:
                        _, stop_id = internal_id.split(':', 1)
                        active_stops.append(stop_id)
            result['active_stops'] = active_stops
            
            return result
        except Exception as e:
            logger.error(f"Error getting state: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def simulate_key_on(self, manual: str, note: int) -> Dict[str, Any]:
        """Simulate a key press.
        
        Args:
            manual: Manual code (G/S/C/P for Great/Swell/Choir/Pedal)
            note: MIDI note number (0-127)
        
        Returns:
            dict with 'success' (bool), 'manual' (str), 'note' (int), and optional 'error' (str)
        """
        try:
            import time
            
            manual = manual.upper()
            manual_map = {'G': 'great', 'S': 'swell', 'C': 'choir', 'P': 'pedal'}
            
            if manual not in manual_map:
                return {
                    'success': False,
                    'error': f'Invalid manual: {manual}. Use G/S/C/P'
                }
            
            if not 0 <= note <= 127:
                return {
                    'success': False,
                    'error': f'Invalid note: {note}. Must be 0-127'
                }
            
            division = manual_map[manual]
            velocity = 64  # Default velocity
            
            # Track key press in state
            self.controller.active_keys[(division, note)] = time.time()
            
            # Route through stop logic
            if self.controller.stop_router:
                self.controller.stop_router.process_note_on(division, note, velocity)
                return {
                    'success': True,
                    'manual': manual,
                    'division': division,
                    'note': note,
                    'velocity': velocity
                }
            else:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
        except Exception as e:
            logger.error(f"Error simulating key on: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def simulate_key_off(self, manual: str, note: int) -> Dict[str, Any]:
        """Simulate a key release.
        
        Args:
            manual: Manual code (G/S/C/P for Great/Swell/Choir/Pedal)
            note: MIDI note number (0-127)
        
        Returns:
            dict with 'success' (bool), 'manual' (str), 'note' (int), and optional 'error' (str)
        """
        try:
            manual = manual.upper()
            manual_map = {'G': 'great', 'S': 'swell', 'C': 'choir', 'P': 'pedal'}
            
            if manual not in manual_map:
                return {
                    'success': False,
                    'error': f'Invalid manual: {manual}. Use G/S/C/P'
                }
            
            if not 0 <= note <= 127:
                return {
                    'success': False,
                    'error': f'Invalid note: {note}. Must be 0-127'
                }
            
            division = manual_map[manual]
            
            # Track key release in state
            self.controller.active_keys.pop((division, note), None)
            
            # Route through stop logic
            if self.controller.stop_router:
                self.controller.stop_router.process_note_off(division, note)
                return {
                    'success': True,
                    'manual': manual,
                    'division': division,
                    'note': note
                }
            else:
                return {
                    'success': False,
                    'error': 'Stop router not initialized'
                }
        except Exception as e:
            logger.error(f"Error simulating key off: {e}")
            return {
                'success': False,
                'error': str(e)
            }
