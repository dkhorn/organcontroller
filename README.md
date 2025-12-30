# Organ Controller

A Raspberry Pi 5-based master controller for pipe organs.

## Overview

This project implements a real-time master controller that:

- **Receives inputs** via CAN bus (console) and USB-MIDI
- **Processes organ logic** including stops, couplers, pistons, and manual assignments
- **Outputs MIDI** to physical organ ranks or sample-based synthesizers
- **Hosts FluidSynth** (optional) for software-based sound generation
- **Exposes REST API** for remote control and monitoring
- **Runs as systemd service** for reliable startup and management

## Project Structure

- `docs/` - Architecture and protocol documentation
- `config/` - YAML configuration files for organ specification
- `scripts/` - Shell scripts for system startup and development
- `systemd/` - Service definitions for systemd integration
- `src/` - Python source code modules
- `soundfonts/` - SoundFont files for FluidSynth
- `tools/` - Diagnostic and testing utilities

## Goals

- Minimal dependencies (Python standard library only for core logic)
- Low-latency MIDI processing
- Modular design for testing and maintenance
- Clear separation of input, logic, and output layers
