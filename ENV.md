# Pool Cue Configuration Reference

Environment settings, configuration options, and production checklist.

## Server Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Development Port | 5002 | start_dev.command |
| Database Path | app/db/pool_queue.db | database.py:10 |
| Static Files | app/static/ | Flask default |
| Templates | app/templates/ | Flask default |

## Key Configuration Flags

### routes_auth.py

```python
# Line 44
BETA_SHOW_CODE = True  # ⚠️ Set to False for production!
```
When True: Shows verification code on screen (for testing)
When False: Code only sent via SMS/email

### database.py

```python
# Line 10
DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'pool_queue.db')
```

## Integration Placeholders (TODO)

| Feature | Location | Status |
|---------|----------|--------|
| SMS (Twilio) | database.py:2164 | Placeholder |
| Stripe Payments | marketer_system.py:171, 605 | Placeholder |
| Email (SendGrid) | routes_auth.py:765 | Placeholder |
| POS (Square/Toast) | pos_connectors/ | Basic implementation |

## Production Checklist

### Before Launch

- [ ] Set `BETA_SHOW_CODE = False` in routes_auth.py:44
- [ ] Configure real SMS provider (Twilio)
- [ ] Configure real email provider (SendGrid/Mailgun)
- [ ] Set up Stripe for payments
- [ ] Backup database
- [ ] Set up SSL certificates
- [ ] Configure proper SECRET_KEY in app.py

### Security

- [ ] Verify all admin routes require authentication
- [ ] Check rate limiting is enabled
- [ ] Confirm CSRF protection active
- [ ] Review exposed API endpoints

## Flask App Configuration

Located in `app/app.py`:

```python
app.secret_key = 'your-secret-key'  # Change for production!
```

## File Locations

```
PoolCue/backend/
├── app/
│   ├── db/
│   │   └── pool_queue.db      # Main database
│   ├── static/
│   │   ├── ads/               # Ad images by placement
│   │   ├── css/               # Stylesheets
│   │   └── icons/             # App icons
│   └── templates/             # All HTML templates
├── run.py                     # Flask entry point
├── requirements.txt           # Python dependencies
└── start_dev.command          # macOS launcher
```

## Starting the Server

**Development:**
```bash
# Option 1: Double-click
./start_dev.command

# Option 2: Command line
cd PoolCue/backend
source venv/bin/activate
python run.py
```

Opens: http://127.0.0.1:5002/master

## Common Ports

| Service | Port |
|---------|------|
| Development | 5002 |
| Beta Testing | 5050 (deprecated) |

## Database Backup

```bash
# Create backup
cp app/db/pool_queue.db app/db/backups/pool_queue_$(date +%Y%m%d).db

# Restore from backup
cp app/db/backups/pool_queue_YYYYMMDD.db app/db/pool_queue.db
```

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-12 | Initial configuration reference created |
