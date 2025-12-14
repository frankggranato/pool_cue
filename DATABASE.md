# Pool Cue Database Reference

Quick reference for database tables and key columns.

## Core Tables

### players
Primary user table - all player accounts and stats.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| nickname | TEXT | Display name (unique) |
| email | TEXT | Email (unique, optional) |
| phone | TEXT | Phone number |
| password_hash | TEXT | Hashed password |
| total_games | INTEGER | Lifetime games played |
| wins / losses | INTEGER | Win/loss counts |
| tokens_balance | INTEGER | Current token balance |
| rating | INTEGER | ELO rating (default 1000) |
| division | TEXT | Bronze/Silver/Gold/etc |
| home_bar_id | INTEGER | FK to bars |
| privacy_mode | INTEGER | 0=public, 1=private |
| is_active | INTEGER | Account active flag |
| phone_verified | INTEGER | Phone verification status |
| email_verified | INTEGER | Email verification status |

### bars
Venue/location table.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| name | TEXT | Bar name |
| address/city/state/zip | TEXT | Location |
| lat/lng | REAL | Coordinates |
| table_count | INTEGER | Number of pool tables |
| is_active | INTEGER | Active flag |
| google_review_url | TEXT | Google review link |
| pos_provider | TEXT | POS system (Square/Toast) |

### queue
Current queue entries for each bar.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| player_id | INTEGER | FK to players |
| bar_id | INTEGER | FK to bars |
| position | INTEGER | Queue position (1=king) |
| status | TEXT | waiting/playing/removed |
| wins_on_table | INTEGER | Consecutive wins |
| session_token | TEXT | Browser session ID |
| partner_name | TEXT | Doubles partner |
| ranked_request | INTEGER | Shot caller requested ranked |
| ranked_accepted | INTEGER | Challenger accepted ranked |
| table_id | INTEGER | Which table (multi-table bars) |

### game_history
Record of all completed games.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| winner_id | INTEGER | FK to players |
| loser_id | INTEGER | FK to players |
| bar_id | INTEGER | FK to bars |
| is_ranked | INTEGER | 0=casual, 1=ranked |
| ranked_source | TEXT | event/window/request |
| played_at | DATETIME | Game timestamp |
| rating_change | INTEGER | ELO points changed |

## Advertising Tables

### advertisers
Advertiser accounts.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| name | TEXT | Company name |
| email | TEXT | Contact email |
| credit_balance | REAL | Ad credits |

### campaigns
Ad campaigns.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| advertiser_id | INTEGER | FK to advertisers |
| name | TEXT | Campaign name |
| status | TEXT | draft/pending/active/paused |
| placement | TEXT | display/join/player |
| daily_budget | REAL | Spend limit |
| start_date/end_date | DATE | Campaign dates |

### ad_events
Impression and click tracking.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| campaign_id | INTEGER | FK to campaigns |
| event_type | TEXT | impression/click |
| bar_id | INTEGER | Where shown |
| player_id | INTEGER | Who saw it |
| created_at | DATETIME | Timestamp |

## Social Tables

### friendships
Friend connections between players.

| Column | Type | Purpose |
|--------|------|---------|
| player_id | INTEGER | Requester |
| friend_id | INTEGER | Recipient |
| status | TEXT | pending/accepted |

### challenges
Player-to-player challenges.

| Column | Type | Purpose |
|--------|------|---------|
| challenger_user_id | INTEGER | Who sent |
| challenged_user_id | INTEGER | Who received |
| status | TEXT | pending/accepted/declined |
| bar_id | INTEGER | Where to play |

## Event Tables

### pool_nights
Scheduled pool night events.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| bar_id | INTEGER | FK to bars |
| host_player_id | INTEGER | Who's hosting |
| event_date | DATE | When |
| status | TEXT | pending/approved/cancelled |
| is_ranked | INTEGER | Ranked event flag |
| is_tournament | INTEGER | Tournament mode |

### tournament_matches
Tournament bracket matches.

| Column | Type | Purpose |
|--------|------|---------|
| pool_night_id | INTEGER | FK to pool_nights |
| round_number | INTEGER | Tournament round |
| player1_id / player2_id | INTEGER | Competitors |
| winner_id | INTEGER | Match winner |
| status | TEXT | pending/in_progress/complete |

## Auth Tables

### user_accounts
Login accounts (separate from player profiles).

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Primary key |
| player_id | INTEGER | FK to players |
| email | TEXT | Login email |
| password_hash | TEXT | Hashed password |

### verifications
Phone/email verification codes.

| Column | Type | Purpose |
|--------|------|---------|
| player_id | INTEGER | FK to players |
| channel | TEXT | phone/email |
| code | TEXT | 6-digit code |
| expires_at | DATETIME | Expiration |

---

## Table Count: 106 tables

## Key Relationships

```
players ─┬─> queue (player_id)
         ├─> game_history (winner_id, loser_id)
         ├─> friendships (player_id, friend_id)
         ├─> challenges (challenger/challenged_user_id)
         └─> token_transactions (player_id)

bars ────┬─> queue (bar_id)
         ├─> game_history (bar_id)
         ├─> pool_nights (bar_id)
         └─> settings (bar_id)

advertisers ─> campaigns ─> ad_events
```

---

## Change Log

| Date | Change |
|------|--------|
| 2025-12-12 | Initial database reference created |
