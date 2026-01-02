import React, { useState, useEffect } from 'react';
import './App.css';

// Use window location hostname for API calls
const API_BASE = `http://${window.location.hostname}:5000/api`;

function App() {
  const [stops, setStops] = useState([]);
  const [activeStops, setActiveStops] = useState(new Set());
  const [status, setStatus] = useState(null);
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch all stops on mount
  useEffect(() => {
    fetchStops();
    fetchStatus();
    fetchState();
    
    // Poll for updates every 500ms
    const interval = setInterval(() => {
      fetchState();
    }, 500);
    
    return () => clearInterval(interval);
  }, []);

  const fetchStops = async () => {
    try {
      const response = await fetch(`${API_BASE}/stops`);
      const data = await response.json();
      setStops(data.stops);
      const active = new Set(data.stops.filter(s => s.active).map(s => s.id));
      setActiveStops(active);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching stops:', error);
      setLoading(false);
    }
  };

  const fetchStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/status`);
      const data = await response.json();
      setStatus(data);
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const fetchState = async () => {
    try {
      const response = await fetch(`${API_BASE}/state`);
      const data = await response.json();
      setState(data);
      // Update active stops from state
      setActiveStops(new Set(data.active_stops));
    } catch (error) {
      console.error('Error fetching state:', error);
    }
  };

  const toggleStop = async (stopId) => {
    const isActive = activeStops.has(stopId);
    const endpoint = isActive ? 'off' : 'on';
    
    try {
      const response = await fetch(`${API_BASE}/stops/${stopId}/${endpoint}`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data.success) {
        const newActive = new Set(activeStops);
        if (isActive) {
          newActive.delete(stopId);
        } else {
          newActive.add(stopId);
        }
        setActiveStops(newActive);
      }
    } catch (error) {
      console.error(`Error toggling stop ${stopId}:`, error);
    }
  };

  const allClear = async () => {
    try {
      const response = await fetch(`${API_BASE}/stops/all-clear`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data.success) {
        setActiveStops(new Set());
      }
    } catch (error) {
      console.error('Error clearing stops:', error);
    }
  };

  const panic = async () => {
    try {
      const response = await fetch(`${API_BASE}/panic`, {
        method: 'POST'
      });
      const data = await response.json();
      
      if (data.success) {
        setActiveStops(new Set());
        console.log(`MIDI panic sent to ${data.outputs_count} outputs`);
      }
    } catch (error) {
      console.error('Error sending panic:', error);
    }
  };

  // Group stops by division (uppercase the division key)
  const stopsByDivision = stops.reduce((acc, stop) => {
    const divisionKey = stop.division.toUpperCase();
    if (!acc[divisionKey]) {
      acc[divisionKey] = [];
    }
    acc[divisionKey].push(stop);
    return acc;
  }, {});

  const divisions = ['GREAT', 'SWELL', 'CHOIR', 'PEDAL'];

  if (loading) {
    return <div className="App"><div className="loading">Loading...</div></div>;
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>🎹 Organ Controller</h1>
        <div className="status-bar">
          {status && (
            <>
              <span className="status-item">
                Active Keys: {state?.keys?.length || 0}
              </span>
              <span className="status-item">
                Playing Notes: {state?.notes?.length || 0}
              </span>
              <span className="status-item">
                Drawn Stops: {activeStops.size}
              </span>
            </>
          )}
        </div>
      </header>

      <div className="controls">
        <button onClick={allClear} className="all-clear-btn">
          All Clear
        </button>
        <button onClick={panic} className="panic-btn" style={{ marginLeft: '10px', backgroundColor: '#dc3545' }}>
          🚨 PANIC
        </button>
      </div>

      <div className="divisions-container">
        {divisions.map(division => (
          <div key={division} className="division">
            <h2>{division}</h2>
            <div className="stops-grid">
              {stopsByDivision[division]?.map(stop => (
                <button
                  key={stop.id}
                  className={`stop-button ${activeStops.has(stop.id) ? 'active' : ''}`}
                  onClick={() => toggleStop(stop.id)}
                >
                  <span className="stop-name">{stop.name}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {state && state.keys && state.keys.length > 0 && (
        <div className="state-panel">
          <h3>Active Keys</h3>
          <div className="keys-list">
            {state.keys.map((key, idx) => {
              const duration = (Date.now() / 1000) - key.timestamp;
              return (
                <div key={idx} className="key-item">
                  {key.division}: Note {key.note} ({duration.toFixed(1)}s)
                </div>
              );
            })}
          </div>
        </div>
      )}

      {state && state.notes && state.notes.length > 0 && (
        <div className="state-panel">
          <h3>Active Rank Notes</h3>
          <div className="notes-list">
            {state.notes.map((note, idx) => {
              const duration = (Date.now() / 1000) - note.timestamp;
              return (
                <div key={idx} className="note-item">
                  {note.rank}: Note {note.note} Ch{note.channel} ({duration.toFixed(1)}s)
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
