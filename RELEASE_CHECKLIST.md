# Pool Cue - Release Checklist

## Before Every Release

### 1. Version Bump
- [ ] Update version in `app/__init__.py` or `run.py`
- [ ] Version format: `MAJOR.MINOR.PATCH` (e.g., 1.2.3)
  - MAJOR: Breaking changes
  - MINOR: New features
  - PATCH: Bug fixes

### 2. Smoke Tests (Happy Path)
Run these manually before each release:

#### Player Flow
- [ ] Scan QR code → Join queue
- [ ] View position in queue
- [ ] See queue update when position changes
- [ ] Leave queue works
- [ ] Login/logout works

#### Bar Manager Flow
- [ ] Login at `/bar-manager/login`
- [ ] View queue for their bar
- [ ] Remove player from queue
- [ ] Cannot access other bars

#### Admin Flow
- [ ] Login at `/admin/login`
- [ ] Dashboard loads with stats
- [ ] Can view all bars
- [ ] Can create bar manager

#### Board Display
- [ ] Board shows current queue
- [ ] Updates automatically
- [ ] Shows match results

### 3. Automated Tests
```bash
cd ~/Desktop/pool_queue_app
pytest tests/ -v
```

### 4. Database
- [ ] Backup database before major releases
- [ ] Test migrations on staging first

### 5. Release Notes
Format:
```
## v1.2.3 - YYYY-MM-DD

### Added
- New feature X

### Fixed
- Bug in Y

### Changed
- Updated Z behavior
```

### 6. Deploy
```bash
# For Railway/Render: just push to main
git checkout main
git merge dev
git push origin main
```

### 7. Post-Deploy Verification
- [ ] App loads (no 500 errors)
- [ ] Can login
- [ ] Queue functions work
- [ ] Check error logs

---

## If Something Breaks

**Rule: Roll forward, don't roll back.**

1. **Identify** the issue from logs
2. **Fix** on a hotfix branch
3. **Test** locally
4. **Deploy** the fix immediately
5. **Document** what went wrong

```bash
# Emergency hotfix workflow
git checkout main
git checkout -b hotfix/urgent-fix
# make fix
git add .
git commit -m "hotfix: fix critical issue"
git checkout main
git merge hotfix/urgent-fix
git push origin main
```

---

## Crash Reporting Setup

### Option 1: Sentry (Recommended)
```bash
pip install sentry-sdk[flask]
```

```python
# In app.py
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.1,
    environment=os.environ.get('FLASK_ENV', 'development')
)
```

### Option 2: Simple Error Logging
```python
# Already in your app - check logs/
import logging
logging.basicConfig(filename='app.log', level=logging.ERROR)
```

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2024-XX-XX | Initial release |
