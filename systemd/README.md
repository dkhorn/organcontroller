# Systemd Service Installation

## Install Services

To install and enable the services to run automatically at boot:

```bash
# Copy service files to systemd directory
sudo cp /home/daniel/organcontroller/systemd/*.service /etc/systemd/system/

# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable services to start at boot
sudo systemctl enable fluidsynth.service
sudo systemctl enable organ-master.service

# Start services now
sudo systemctl start fluidsynth.service
sudo systemctl start organ-master.service
```

## Service Commands

```bash
# Check status
sudo systemctl status fluidsynth.service
sudo systemctl status organ-master.service

# View logs
sudo journalctl -u fluidsynth.service -f
sudo journalctl -u organ-master.service -f

# Stop services
sudo systemctl stop organ-master.service
sudo systemctl stop fluidsynth.service

# Restart services
sudo systemctl restart fluidsynth.service
sudo systemctl restart organ-master.service

# Disable autostart
sudo systemctl disable fluidsynth.service
sudo systemctl disable organ-master.service
```

## Service Dependencies

- `fluidsynth.service` starts first and creates the virtual MIDI port
- `organ-master.service` depends on FluidSynth and waits 2 seconds for the port to be ready
