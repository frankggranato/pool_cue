"""
RBAC Migration Script
Creates new tables for Role-Based Access Control

Run this ONCE to set up the RBAC system.
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'app/db/pool_queue.db')

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("🔐 Starting RBAC Migration...")
    
    # ============================================
    # 1. CREATE NEW TABLES
    # ============================================
    
    # Users table (unified authentication)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            is_superadmin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✅ Created users table")
    
    # Roles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            level INTEGER DEFAULT 0,
            is_system_role INTEGER DEFAULT 1
        )
    ''')
    print("✅ Created roles table")
    
    # Permissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            category TEXT
        )
    ''')
    print("✅ Created permissions table")
    
    # Role-Permission mapping
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (permission_id) REFERENCES permissions(id)
        )
    ''')
    print("✅ Created role_permissions table")

    # User-Venue-Role mapping
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_venue_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            venue_id INTEGER,
            role_id INTEGER NOT NULL,
            assigned_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (venue_id) REFERENCES bars(id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            UNIQUE(user_id, venue_id, role_id)
        )
    ''')
    print("✅ Created user_venue_roles table")
    
    # Add user_id column to players table if not exists
    cursor.execute("PRAGMA table_info(players)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'user_id' not in columns:
        cursor.execute('ALTER TABLE players ADD COLUMN user_id INTEGER REFERENCES users(id)')
        print("✅ Added user_id to players table")
    
    # ============================================
    # 2. INSERT DEFAULT ROLES
    # ============================================
    
    roles = [
        ('superadmin', 'System administrator with full access', 100),
        ('owner', 'Venue owner with full venue access', 90),
        ('manager', 'Venue manager - staff and operations', 70),
        ('staff', 'Venue staff - board operations only', 50),
        ('analyst', 'Analytics viewer - read-only reports', 30),
        ('player', 'Customer/Player role', 10),
    ]
    
    for name, desc, level in roles:
        cursor.execute('''
            INSERT OR IGNORE INTO roles (name, description, level, is_system_role)
            VALUES (?, ?, ?, 1)
        ''', (name, desc, level))
    print("✅ Inserted default roles")
    
    # ============================================
    # 3. INSERT PERMISSIONS
    # ============================================
    
    permissions = [
        # Analytics
        ('can_view_analytics', 'View venue analytics and reports', 'analytics'),
        ('can_export_data', 'Export analytics data', 'analytics'),
        
        # Staff Management
        ('can_manage_staff', 'Add/remove/edit staff members', 'staff'),
        ('can_assign_roles', 'Assign roles to users', 'staff'),
        
        # Board Operations
        ('can_operate_board', 'Control the queue board', 'board'),
        ('can_manage_queue', 'Add/remove players from queue', 'board'),
        ('can_record_games', 'Record game results', 'board'),
        
        # Venue Settings
        ('can_edit_venue_settings', 'Change venue settings', 'venue'),
        ('can_manage_tables', 'Add/remove/edit tables', 'venue'),
        ('can_view_financials', 'View revenue and financial data', 'venue'),
        
        # Events
        ('can_run_pool_nights', 'Create/manage pool night events', 'events'),
        ('can_manage_tournaments', 'Create/manage tournaments', 'events'),
        
        # Players (admin only)
        ('can_manage_players', 'View/edit player accounts', 'admin'),
        ('can_view_all_venues', 'View all venues in system', 'admin'),
        ('can_manage_venues', 'Create/edit/delete venues', 'admin'),
        ('can_access_master', 'Access master admin dashboard', 'admin'),
        ('can_manage_advertisers', 'Manage advertising platform', 'admin'),
    ]
    
    for name, desc, category in permissions:
        cursor.execute('''
            INSERT OR IGNORE INTO permissions (name, description, category)
            VALUES (?, ?, ?)
        ''', (name, desc, category))
    print("✅ Inserted permissions")

    # ============================================
    # 4. MAP ROLES TO PERMISSIONS
    # ============================================
    
    role_permission_map = {
        'superadmin': [
            'can_view_analytics', 'can_export_data', 'can_manage_staff', 'can_assign_roles',
            'can_operate_board', 'can_manage_queue', 'can_record_games', 'can_edit_venue_settings',
            'can_manage_tables', 'can_view_financials', 'can_run_pool_nights', 'can_manage_tournaments',
            'can_manage_players', 'can_view_all_venues', 'can_manage_venues', 'can_access_master',
            'can_manage_advertisers'
        ],
        'owner': [
            'can_view_analytics', 'can_export_data', 'can_manage_staff', 'can_assign_roles',
            'can_operate_board', 'can_manage_queue', 'can_record_games', 'can_edit_venue_settings',
            'can_manage_tables', 'can_view_financials', 'can_run_pool_nights', 'can_manage_tournaments'
        ],
        'manager': [
            'can_view_analytics', 'can_manage_staff', 'can_operate_board', 'can_manage_queue',
            'can_record_games', 'can_manage_tables', 'can_run_pool_nights'
        ],
        'staff': [
            'can_operate_board', 'can_manage_queue', 'can_record_games'
        ],
        'analyst': [
            'can_view_analytics', 'can_export_data'
        ],
        'player': []  # Players don't need venue permissions
    }
    
    for role_name, perms in role_permission_map.items():
        cursor.execute('SELECT id FROM roles WHERE name = ?', (role_name,))
        role = cursor.fetchone()
        if role:
            for perm_name in perms:
                cursor.execute('SELECT id FROM permissions WHERE name = ?', (perm_name,))
                perm = cursor.fetchone()
                if perm:
                    cursor.execute('''
                        INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
                        VALUES (?, ?)
                    ''', (role['id'], perm['id']))
    print("✅ Mapped roles to permissions")
    
    # ============================================
    # 5. MIGRATE EXISTING DATA
    # ============================================
    
    # Migrate admin_accounts to users
    cursor.execute('SELECT * FROM admin_accounts')
    admins = cursor.fetchall()
    superadmin_role_id = cursor.execute('SELECT id FROM roles WHERE name = ?', ('superadmin',)).fetchone()['id']
    
    for admin in admins:
        admin = dict(admin)
        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (admin.get('email') or f"admin_{admin['id']}@poolcue.local",))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, is_active, is_superadmin, created_at)
                VALUES (?, ?, ?, 1, 1, ?)
            ''', (
                admin.get('email') or f"admin_{admin['id']}@poolcue.local",
                admin['password_hash'],
                admin.get('username', 'Admin'),
                admin.get('created_at', 'now')
            ))
            user_id = cursor.lastrowid
            # Assign superadmin role (global)
            cursor.execute('''
                INSERT OR IGNORE INTO user_venue_roles (user_id, venue_id, role_id)
                VALUES (?, NULL, ?)
            ''', (user_id, superadmin_role_id))
    print(f"✅ Migrated {len(admins)} admin accounts")

    # Migrate bar_managers to users
    cursor.execute('SELECT * FROM bar_managers')
    managers = cursor.fetchall()
    manager_role_id = cursor.execute('SELECT id FROM roles WHERE name = ?', ('manager',)).fetchone()['id']
    
    for mgr in managers:
        mgr = dict(mgr)
        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (mgr['email'],))
        existing = cursor.fetchone()
        
        if existing:
            user_id = existing['id']
        else:
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, is_active, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                mgr['email'],
                mgr['password_hash'],
                mgr.get('name', mgr['email']),
                mgr.get('is_active', 1),
                mgr.get('created_at', 'now')
            ))
            user_id = cursor.lastrowid
        
        # Assign role for their venue
        cursor.execute('''
            INSERT OR IGNORE INTO user_venue_roles (user_id, venue_id, role_id)
            VALUES (?, ?, ?)
        ''', (user_id, mgr['bar_id'], manager_role_id))
    print(f"✅ Migrated {len(managers)} bar managers")
    
    # Link existing players with accounts to users table
    cursor.execute('''
        SELECT p.id, p.nickname, a.email, a.password_hash, p.created_at
        FROM players p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.account_id IS NOT NULL
    ''')
    players_with_accounts = cursor.fetchall()
    player_role_id = cursor.execute('SELECT id FROM roles WHERE name = ?', ('player',)).fetchone()['id']
    
    for player in players_with_accounts:
        player = dict(player)
        # Check if email already exists in users
        cursor.execute('SELECT id FROM users WHERE email = ?', (player['email'],))
        existing = cursor.fetchone()
        
        if existing:
            user_id = existing['id']
        else:
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, created_at)
                VALUES (?, ?, ?, ?)
            ''', (player['email'], player['password_hash'], player['nickname'], player['created_at']))
            user_id = cursor.lastrowid
        
        # Update player record with user_id
        cursor.execute('UPDATE players SET user_id = ? WHERE id = ?', (user_id, player['id']))
        
        # Assign player role (global)
        cursor.execute('''
            INSERT OR IGNORE INTO user_venue_roles (user_id, venue_id, role_id)
            VALUES (?, NULL, ?)
        ''', (user_id, player_role_id))
    
    print(f"✅ Linked {len(players_with_accounts)} player accounts")
    
    conn.commit()
    conn.close()
    
    print("\n🎉 RBAC Migration Complete!")
    print("\nNext steps:")
    print("1. Test login at /auth/unified-login")
    print("2. Superadmin can assign roles at /master/users")


if __name__ == '__main__':
    run_migration()
