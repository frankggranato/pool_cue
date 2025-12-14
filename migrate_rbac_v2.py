"""
RBAC Schema Migration v2
Aligns with the cleaner data model:
- Users (with status enum)
- Venues (using existing bars table)
- UserVenueRoles (simplified with role string)
- AuditLog (comprehensive logging)
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'app/db/pool_queue.db')

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("🔐 RBAC Schema Migration v2")
    print("=" * 50)
    
    # ============================================
    # 1. UPDATE USERS TABLE
    # ============================================
    print("\n📋 Updating users table...")
    
    # Add status column (active/suspended/pending)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
        print("  ✅ Added status column")
    except:
        print("  ⏭️  status column exists")
    
    # Add email_verified column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
        print("  ✅ Added email_verified column")
    except:
        print("  ⏭️  email_verified column exists")
    
    # Add last_login column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_login TIMESTAMP")
        print("  ✅ Added last_login column")
    except:
        print("  ⏭️  last_login column exists")
    
    # Add verification_token column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
        print("  ✅ Added verification_token column")
    except:
        print("  ⏭️  verification_token column exists")
    
    # Add verification_token_expires column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN verification_token_expires TIMESTAMP")
        print("  ✅ Added verification_token_expires column")
    except:
        print("  ⏭️  verification_token_expires column exists")
    
    # Add reset_token column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
        print("  ✅ Added reset_token column")
    except:
        print("  ⏭️  reset_token column exists")
    
    # Add reset_token_expires column
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP")
        print("  ✅ Added reset_token_expires column")
    except:
        print("  ⏭️  reset_token_expires column exists")
    
    # Migrate is_active to status
    cursor.execute("UPDATE users SET status = 'active' WHERE is_active = 1 AND status IS NULL")
    cursor.execute("UPDATE users SET status = 'suspended' WHERE is_active = 0 AND status IS NULL")
    print("  ✅ Migrated is_active to status")

    # ============================================
    # 2. CREATE SIMPLIFIED USER_VENUE_ROLES TABLE
    # ============================================
    print("\n📋 Creating user_venue_roles_v2 table...")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_venue_roles_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            venue_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'manager', 'staff', 'analyst')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_by INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (venue_id) REFERENCES bars(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_by) REFERENCES users(id),
            UNIQUE(user_id, venue_id)
        )
    ''')
    print("  ✅ Created user_venue_roles_v2 table")
    
    # Migrate existing data from old table
    cursor.execute('''
        INSERT OR IGNORE INTO user_venue_roles_v2 (user_id, venue_id, role, created_at, assigned_by)
        SELECT 
            uvr.user_id,
            uvr.venue_id,
            CASE r.name
                WHEN 'superadmin' THEN 'owner'
                WHEN 'owner' THEN 'owner'
                WHEN 'bar_owner' THEN 'owner'
                WHEN 'manager' THEN 'manager'
                WHEN 'bar_manager' THEN 'manager'
                WHEN 'staff' THEN 'staff'
                WHEN 'bar_staff' THEN 'staff'
                WHEN 'analyst' THEN 'analyst'
                ELSE 'staff'
            END as role,
            uvr.created_at,
            uvr.assigned_by
        FROM user_venue_roles uvr
        JOIN roles r ON uvr.role_id = r.id
        WHERE uvr.venue_id IS NOT NULL
    ''')
    print("  ✅ Migrated existing venue roles")
    
    # ============================================
    # 3. CREATE AUDIT_LOG TABLE
    # ============================================
    print("\n📋 Creating audit_log table...")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            target_user_id INTEGER,
            venue_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details_json TEXT,
            ip_address TEXT,
            FOREIGN KEY (actor_user_id) REFERENCES users(id),
            FOREIGN KEY (target_user_id) REFERENCES users(id),
            FOREIGN KEY (venue_id) REFERENCES bars(id)
        )
    ''')
    print("  ✅ Created audit_log table")
    
    # Create index for fast lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log(target_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_venue ON audit_log(venue_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)')
    print("  ✅ Created audit_log indexes")

    # ============================================
    # 4. CREATE INVITE TOKENS TABLE
    # ============================================
    print("\n📋 Creating invite_tokens table...")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            venue_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'manager', 'staff', 'analyst')),
            invited_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            accepted_at TIMESTAMP,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'expired', 'revoked')),
            FOREIGN KEY (venue_id) REFERENCES bars(id),
            FOREIGN KEY (invited_by) REFERENCES users(id)
        )
    ''')
    print("  ✅ Created invite_tokens table")
    
    # ============================================
    # 5. CREATE USER_SESSIONS TABLE (for invalidation)
    # ============================================
    print("\n📋 Creating user_sessions table...")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            is_valid INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    print("  ✅ Created user_sessions table")
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)')
    print("  ✅ Created user_sessions indexes")
    
    # ============================================
    # 6. FINALIZE
    # ============================================
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 50)
    print("🎉 Migration complete!")
    print("\nTables created/updated:")
    print("  - users (added status, email_verified, tokens)")
    print("  - user_venue_roles_v2 (simplified role enum)")
    print("  - audit_log (comprehensive logging)")
    print("  - invite_tokens (email invites)")
    print("  - user_sessions (for invalidation)")


if __name__ == '__main__':
    run_migration()
