#!/bin/bash

# Pool Cue - Start Development Server
# Double-click this file to start the app

cd "$(dirname "$0")"

# Get current network IP
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo "🎱 Pool Cue starting on http://$IP:5002"

# Kill any existing server on port 5002
lsof -ti:5002 | xargs kill -9 2>/dev/null

# Activate virtual environment
source venv/bin/activate

# Open browser after a short delay
(sleep 2 && open "http://$IP:5002/master") &

# Start Flask server (bind to all interfaces for mobile access)
python run.py --host=0.0.0.0
