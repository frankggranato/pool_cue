#!/bin/bash

# Pool Cue - Start Development Server
# Double-click this file to start the app

cd "$(dirname "$0")"

# Kill any existing server on port 5002
lsof -ti:5002 | xargs kill -9 2>/dev/null

# Activate virtual environment
source venv/bin/activate

# Open browser after a short delay (opens master dashboard)
(sleep 2 && open http://127.0.0.1:5002/master) &

# Start Flask server
python run.py
