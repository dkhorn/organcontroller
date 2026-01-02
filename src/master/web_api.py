"""Web API for organ controller.

Provides REST endpoints for status, control, and state monitoring.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import time
from typing import Optional
import logging
from .actions import Actions

logger = logging.getLogger('organcontroller.api')


class OrganWebAPI:
    """Web API server for organ controller."""
    
    def __init__(self, controller, host='0.0.0.0', port=5000):
        """Initialize the web API.
        
        Args:
            controller: Reference to OrganController instance
            host: Host to bind to (default: 0.0.0.0 for all interfaces)
            port: Port to bind to (default: 5000)
        """
        self.controller = controller
        self.actions = Actions(controller)
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for React frontend
        
        self._setup_routes()
        self.server_thread: Optional[threading.Thread] = None
        
    def _setup_routes(self):
        """Set up API routes."""
        
        @self.app.route('/api/health', methods=['GET'])
        def health():
            """Health check endpoint."""
            return jsonify({
                'status': 'ok',
                'running': self.controller.running,
                'timestamp': time.time()
            })
        
        @self.app.route('/api/status', methods=['GET'])
        def status():
            """Get system status."""
            result = self.actions.get_status()
            if result['success']:
                return jsonify({
                    'active_stops': result['active_stops'],
                    'active_keys_count': result['active_keys'],
                    'active_rank_notes_count': result['active_notes']
                })
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
        
        @self.app.route('/api/stops', methods=['GET'])
        def list_stops():
            """Get list of all available stops."""
            result = self.actions.list_stops()
            if result['success']:
                return jsonify({'stops': result['stops']})
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
        
        @self.app.route('/api/stops/active', methods=['GET'])
        def active_stops():
            """Get list of currently active stops."""
            result = self.actions.get_active_stops()
            if result['success']:
                return jsonify({'active_stops': result['stops']})
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
        
        @self.app.route('/api/stops/<stop_id>/on', methods=['POST'])
        def activate_stop(stop_id):
            """Activate a stop."""
            result = self.actions.activate_stop(stop_id)
            status_code = 404 if 'Unknown stop' in result.get('error', '') else 200
            if result['success']:
                logger.info(f"API: Activated stop {result['stop_id']}")
            return jsonify(result), status_code if not result['success'] else 200
        
        @self.app.route('/api/stops/<stop_id>/off', methods=['POST'])
        def deactivate_stop(stop_id):
            """Deactivate a stop."""
            result = self.actions.deactivate_stop(stop_id)
            status_code = 404 if 'Unknown stop' in result.get('error', '') else 200
            if result['success']:
                logger.info(f"API: Deactivated stop {result['stop_id']}")
            return jsonify(result), status_code if not result['success'] else 200
        
        @self.app.route('/api/stops/all-clear', methods=['POST'])
        def all_clear():
            """Deactivate all stops."""
            result = self.actions.all_clear()
            if result['success']:
                logger.info(f"API: All stops cleared ({result['count']} stops)")
                return jsonify(result)
            else:
                return jsonify(result), 500
        
        @self.app.route('/api/panic', methods=['POST'])
        def panic():
            """Send MIDI panic (all notes off) to all outputs."""
            result = self.actions.panic()
            if result['success']:
                logger.info(f"API: MIDI panic sent to {result['outputs_count']} outputs")
                return jsonify(result)
            else:
                return jsonify(result), 500
        
        @self.app.route('/api/state/keys', methods=['GET'])
        def state_keys():
            """Get currently held keys."""
            result = self.actions.get_state('keys')
            if result['success']:
                return jsonify({'keys': result['keys']})
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
        
        @self.app.route('/api/state/notes', methods=['GET'])
        def state_notes():
            """Get currently playing rank notes."""
            result = self.actions.get_state('notes')
            if result['success']:
                return jsonify({'notes': result['notes']})
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
        
        @self.app.route('/api/state', methods=['GET'])
        def state():
            """Get complete state information."""
            result = self.actions.get_state()
            if result['success']:
                return jsonify(result)
            else:
                return jsonify({'error': result.get('error', 'Unknown error')}), 500
    
    def start(self):
        """Start the API server in a background thread."""
        def run_server():
            logger.info(f"Starting web API on {self.host}:{self.port}")
            # Disable Flask's default logging to console (we have our own)
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.WARNING)
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logger.info("Web API server started")
    
    def stop(self):
        """Stop the API server."""
        # Flask doesn't have a clean shutdown method when running in a thread
        # The daemon thread will be stopped when the main program exits
        logger.info("Web API server stopping")
