# 🎱 Pool Cue

Queue management system for pool halls and bars. Players scan a QR code to join the queue, see their position in real-time, and get notified when it's their turn.

## Features

- **Queue Management**: Join, leave, and track queue position
- **Real-time Updates**: Live board display and player status
- **Multi-bar Support**: Manage multiple venues from one dashboard
- **Player Accounts**: Track stats, rankings, and match history
- **Bar Manager Portal**: Staff can manage their bar's queue
- **Advertiser Platform**: Run campaigns on bar displays
- **SMS Notifications**: Optional alerts via Twilio

## Quick Start

```bash
# Clone/navigate to project
cd ~/Desktop/PoolCue/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env

# Run development server
python run.py
```

Visit:
- Player app: http://localhost:5002/join
- Admin dashboard: http://localhost:5002/admin/login
- Board display: http://localhost:5002/display?bar_id=1

## Project Structure

```
PoolCue/backend/
├── app/
│   ├── __init__.py
│   ├── app.py              # Flask app factory
│   ├── config.py           # Configuration loader
│   ├── database.py         # Database operations
│   ├── models.py           # Data models
│   ├── routes_*.py         # Route blueprints
│   ├── templates/          # Jinja2 templates
│   ├── static/             # CSS, JS, images
│   └── db/                 # SQLite database
├── tests/                  # Test suite
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
├── run.py                  # Development server
└── Procfile               # Production server
```

## Documentation

- [ACCESS_CONTROL.md](ACCESS_CONTROL.md) - Permissions and login URLs
- [DEPLOYMENT.md](DEPLOYMENT.md) - Cloud deployment options
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) - Release process
- [SECURITY_FIXES.py](SECURITY_FIXES.py) - Security guidelines

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_integration.py -v
```

## Environment Variables

See `.env.example` for all options. Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | development/staging/production | development |
| `SECRET_KEY` | Session encryption key | (required) |
| `ENABLE_ADS` | Show advertisements | true |
| `ENABLE_SMS_NOTIFICATIONS` | Twilio SMS alerts | false |

## Portals

| Role | URL | Description |
|------|-----|-------------|
| Player | `/login` | Join queues, track stats |
| Bar Manager | `/bar-manager/login` | Manage bar queue |
| Advertiser | `/market/login` | Campaign management |
| Admin | `/admin/login` | System administration |

## License

Proprietary - Pool Cue © 2024
