#!/usr/bin/env python3
"""
Pool Cue - Admin Password Reset Tool

USE THIS IF YOU GET LOCKED OUT!

Run from terminal:
    python reset_admin.py

This will let you:
1. Reset your admin password
2. Create a new admin account
3. List all admin accounts
"""
import sqlite3
import os
import sys
from getpass import getpass
from werkzeug.security import generate_password_hash

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'app', 'db', 'pool_queue.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def list_admins():
    """Show all admin accounts."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, role, is_active, is_superadmin, last_login FROM admin_accounts')
    admins = cursor.fetchall()
    conn.close()
    
    print("\n=== Admin Accounts ===")
    if not admins:
        print("No admin accounts found!")
    for admin in admins:
        status = "✓ Active" if admin['is_active'] else "✗ Inactive"
        super_flag = " [SUPERADMIN]" if admin['is_superadmin'] else ""
        print(f"  ID: {admin['id']} | {admin['username']} | {admin['role']}{super_flag} | {status}")
    print()

def reset_password():
    """Reset password for existing admin."""
    list_admins()
    
    username = input("Enter username to reset: ").strip()
    if not username:
        print("Cancelled.")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM admin_accounts WHERE username = ?', (username,))
    admin = cursor.fetchone()
    
    if not admin:
        print(f"Admin '{username}' not found!")
        conn.close()
        return
    
    print(f"\nResetting password for: {username}")
    password = getpass("New password (min 8 chars): ")
    
    if len(password) < 8:
        print("Password too short! Minimum 8 characters.")
        conn.close()
        return
    
    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match!")
        conn.close()
        return
    
    password_hash = generate_password_hash(password, method='scrypt')
    cursor.execute('UPDATE admin_accounts SET password_hash = ?, is_active = 1 WHERE username = ?', 
                   (password_hash, username))
    conn.commit()
    conn.close()
    
    print(f"\n✓ Password reset for '{username}'!")
    print(f"  Login at: http://localhost:5002/admin/login")

def create_admin():
    """Create a new admin account."""
    print("\n=== Create New Admin ===")
    
    username = input("Username: ").strip()
    if not username:
        print("Cancelled.")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM admin_accounts WHERE username = ?', (username,))
    if cursor.fetchone():
        print(f"Username '{username}' already exists!")
        conn.close()
        return
    
    password = getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password too short!")
        conn.close()
        return
    
    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match!")
        conn.close()
        return
    
    make_super = input("Make superadmin? (y/N): ").lower() == 'y'
    
    password_hash = generate_password_hash(password, method='scrypt')
    cursor.execute('''
        INSERT INTO admin_accounts (username, password_hash, role, is_active, is_superadmin)
        VALUES (?, ?, 'admin', 1, ?)
    ''', (username, password_hash, 1 if make_super else 0))
    conn.commit()
    conn.close()
    
    print(f"\n✓ Admin '{username}' created!")

def emergency_reset():
    """Emergency: Reset the main admin account to a known password."""
    print("\n⚠️  EMERGENCY RESET")
    print("This will reset the 'admin' account password to: poolcue123")
    
    confirm = input("Type 'RESET' to confirm: ")
    if confirm != 'RESET':
        print("Cancelled.")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if admin exists
    cursor.execute('SELECT id FROM admin_accounts WHERE username = ?', ('admin',))
    admin = cursor.fetchone()
    
    password_hash = generate_password_hash('poolcue123', method='scrypt')
    
    if admin:
        cursor.execute('UPDATE admin_accounts SET password_hash = ?, is_active = 1, is_superadmin = 1 WHERE username = ?',
                       (password_hash, 'admin'))
    else:
        cursor.execute('''
            INSERT INTO admin_accounts (username, password_hash, role, is_active, is_superadmin)
            VALUES ('admin', ?, 'master', 1, 1)
        ''', (password_hash,))
    
    conn.commit()
    conn.close()
    
    print("\n✓ Emergency reset complete!")
    print("  Username: admin")
    print("  Password: poolcue123")
    print("  ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")

def main():
    print("\n" + "="*50)
    print("  🎱 Pool Cue - Admin Password Reset Tool")
    print("="*50)
    
    if not os.path.exists(DB_PATH):
        print(f"\n❌ Database not found at: {DB_PATH}")
        print("   Make sure you're running this from the PoolCue/backend folder.")
        sys.exit(1)
    
    while True:
        print("\nOptions:")
        print("  1. List admin accounts")
        print("  2. Reset admin password")
        print("  3. Create new admin")
        print("  4. EMERGENCY RESET (resets to known password)")
        print("  5. Exit")
        
        choice = input("\nChoice (1-5): ").strip()
        
        if choice == '1':
            list_admins()
        elif choice == '2':
            reset_password()
        elif choice == '3':
            create_admin()
        elif choice == '4':
            emergency_reset()
        elif choice == '5':
            print("\nGoodbye! 👋\n")
            break
        else:
            print("Invalid choice.")

if __name__ == '__main__':
    main()
