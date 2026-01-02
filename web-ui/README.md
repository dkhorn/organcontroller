# Organ Controller Web UI

Browser-based interface for controlling the organ system.

## Features

- **Stop Control**: Toggle stops on/off by clicking buttons
- **Live State Monitoring**: Real-time display of active keys and playing notes
- **Division Layout**: Stops organized by Great, Swell, Choir, and Pedal divisions
- **All Clear**: Quickly deactivate all stops
- **Status Bar**: Shows active keys, playing notes, and drawn stops count

## Development

```bash
cd web-ui
npm start
```

The development server will run on `http://localhost:3000` and proxy API requests to `http://localhost:5000`.

## Production Build

```bash
./build.sh
```

This creates optimized static files in the `build/` directory.

## Deployment

### Option 1: nginx on Port 80

1. Install nginx:
   ```bash
   sudo apt install nginx
   ```

2. Copy nginx configuration:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/organcontroller
   sudo ln -s /etc/nginx/sites-available/organcontroller /etc/nginx/sites-enabled/
   sudo rm /etc/nginx/sites-enabled/default  # Remove default site
   ```

3. Restart nginx:
   ```bash
   sudo systemctl restart nginx
   ```

4. Access at `http://<raspberry-pi-ip>/`

### Option 2: Serve with Python

```bash
cd build
python3 -m http.server 80
```

Note: API requests will need CORS configured if serving from different origin.

## API Endpoints

The UI communicates with the Flask backend running on port 5000:

- `GET /api/stops` - List all stops
- `POST /api/stops/<stop_id>/on` - Activate a stop
- `POST /api/stops/<stop_id>/off` - Deactivate a stop
- `POST /api/stops/all-clear` - Deactivate all stops
- `GET /api/status` - Get system status
- `GET /api/state` - Get current state (keys, notes, stops)
- `GET /api/health` - Health check

## Architecture

- **React** - UI framework
- **Create React App** - Build tooling
- **Flask** - Python backend API
- **nginx** - Web server and reverse proxy (production)

## Customization

Edit `src/App.js` to modify functionality and `src/App.css` for styling.

The UI polls the state endpoint every 500ms to update the display with currently held keys and playing notes.
