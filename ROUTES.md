# Pool Cue Route Map
Quick reference for all API endpoints and pages.

## Route Files Overview

| File | Prefix | Purpose |
|------|--------|---------|
| routes_public.py | `/` | Join queue, player status, QR scan |
| routes_player.py | `/player` | Player app (home, profile, friends) |
| routes_master.py | `/master` | Admin dashboard |
| routes_admin.py | `/admin` | Bar manager (legacy) |
| routes_board.py | `/board` | TV display controls |
| routes_display.py | `/` | Display board, QR codes |
| routes_auth.py | `/auth` | Login, signup, verification |
| routes_market.py | `/market` | Advertiser portal |
| routes_social.py | `/api/social` | Friends, tokens, challenges |
| routes_api.py | `/api` | General API endpoints |
| routes_apps.py | `/app` | App launchers |
| routes_ad_tracking.py | `/ad` | Ad impressions/clicks |
| routes_brand_admin.py | `/admin/brands` | Brand intelligence |
| routes_setup.py | `/` | Initial setup wizard |

## Key Entry Points

### Player-Facing
- `/player/home` - Player app home
- `/join` - Join queue page
- `/q/{bar_id}` - QR scan landing
- `/my-status` - Current queue status

### Admin
- `/master` - Master dashboard (primary)
- `/admin` - Bar manager (legacy)
- `/market/dashboard` - Advertiser portal

### Display
- `/display` - TV queue board
- `/board/control/{bar_id}` - Board controls

## Template Mapping

| Route | Template |
|-------|----------|
| `/player/home` | `player/home.html` |
| `/player/profile` | `player/profile.html` |
| `/join` | `public/join.html` |
| `/my-status` | `public/player_status.html` |
| `/display` | `board/display.html` |
| `/master` | `master/dashboard.html` |
| `/auth/login` | `auth/login.html` |
| `/auth/signup` | `auth/signup.html` |

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-12 | Initial route map created |
| 2025-12-12 | Removed `/dev` route (dev_dashboard deleted) |
| 2025-12-12 | Templates reorganized into folders |
