#!/usr/bin/env python3
"""
Pool Cue - Development Server Launcher
Run this file to start the app: python run.py

SECURITY NOTE: Debug mode is controlled by FLASK_DEBUG environment variable.
Never set FLASK_DEBUG=true in production!
"""
import sys
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env vars

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.app import create_app

app = create_app()

if __name__ == '__main__':
    # SECURITY: Debug mode controlled by environment variable
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 5002))
    host = os.environ.get('HOST', '0.0.0.0')
    
    # Get local IP for network access
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"
    
    print("\n🎱 Pool Cue Server")
    print("=" * 40)
    print("")
    print(f"  Mode: {'DEVELOPMENT' if debug_mode else 'PRODUCTION'}")
    print(f"  Local:   http://127.0.0.1:{port}/master")
    print(f"  Network: http://{local_ip}:{port}/master")
    print(f"  Board:   http://{local_ip}:{port}/display?bar_id=1")
    print("")
    if debug_mode:
        print("  ⚠️  DEBUG MODE ENABLED - Not for production!")
    print("")
    print("=" * 40)
    print("Press Ctrl+C to stop\n")
    
    app.run(debug=debug_mode, port=port, host=host, threaded=True)
