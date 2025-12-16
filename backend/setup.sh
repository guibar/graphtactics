#!/bin/bash

# Setup script for NEOTac backend
# Supports both pip and UV package managers

# Clone repository (if needed)
# git clone git@github.com:NEOTac/backend.git
# cd backend/ || exit

# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-venv


# Option 1: Install with pip (traditional)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Option 2: Install with UV (faster, uncomment to use)
# uv venv .venv
# source .venv/bin/activate
# pip install uv
# uv pip install -e .

# Set environment variables
source ./vars.env

# Example commands to run the application:
# python3 /app/graphtactics/road_network_factory.py prepare 60
# gunicorn --bind 0.0.0.0:5000 graphtactics.app:app --timeout 80 --log-level debug