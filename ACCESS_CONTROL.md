# Pool Cue - Access Control & Permissions Guide

## Quick Reference

| Role | Login URL | What They Can Do |
|------|-----------|------------------|
| **Superadmin** | `/admin/login` | Everything - full system access |
| **Admin** | `/admin/login` | Master dashboard, all bars, players, settings |
| **Bar Owner** | `/bar-manager/login` | Full access to their bar(s) |
| **Bar Manager** | `/bar-manager/login` | Queue, events, reports for their bar |
| **Bar Staff** | `/bar-manager/login` | Basic queue management |
| **Marketer** | `/market/login` | Ad campaigns, analytics |
| **Player** | `/login` | Play, social features, stats |

## Portal URLs

- **Unified Portal**: `/portal` - Choose your login type
- **Player Login**: `/login`
- **Bar Manager Login**: `/bar-manager/login`
- **Marketer Login**: `/market/login`
- **Admin Login**: `/admin/login`

## Emergency Access

### If you forget your admin password:

```bash
cd ~/Desktop/PoolCue/backend
python reset_admin.py
```

Options:
1. List all admin accounts
2. Reset password for any admin
3. Create new admin account
4. **EMERGENCY RESET** - Resets `admin` to password `poolcue123`

### Beta backdoor (development only):

- Username: `beta`
- Password: `beta`
- Works from: localhost only (or with `ALLOW_BETA_LOGIN=true`)

## Creating Accounts

### Create a Bar Manager:
1. Master Dashboard → Bars → Select Bar
2. Click **👤 Managers** button
3. Fill in email, name, password, role
4. Click Add Manager

### Create an Admin:
```bash
python reset_admin.py
# Choose option 3: Create new admin
```

### Create a Marketer:
Master Dashboard → Advertisers → Create Advertiser
(They set their own password on first login)

## Permission Levels

### Superadmin (is_superadmin = 1)
- Cannot be deleted through the app
- Can only be modified via `reset_admin.py`
- Full access to everything

### Bar Roles
- **Owner**: Full access to their bar, can view all reports
- **Manager**: Queue management, events, basic reports
- **Staff**: Queue management only

## Database Tables

- `admin_accounts` - Master admins (username, password_hash, role, is_superadmin)
- `bar_managers` - Bar staff (email, password_hash, bar_id, role)
- `marketer_accounts` - Advertisers (contact_email, password_hash, business_name)
- `players` - Players (email, password_hash, nickname)

## Environment Variables

```bash
# Production settings
SECRET_KEY=your-secret-key-here
ALLOW_BETA_LOGIN=false
FLASK_DEBUG=false
TWILIO_AUTH_TOKEN=your-twilio-token
```

## Security Notes

1. **Superadmin protection**: Cannot be deleted, even by other admins
2. **Beta login**: Only works from localhost unless explicitly enabled
3. **Session cookies**: HttpOnly, SameSite=Lax (add Secure=True for HTTPS)
4. **Password hashing**: Using scrypt via Werkzeug
5. **SQL injection**: All queries use parameterized statements
