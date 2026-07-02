# database.py
import sqlite3
import threading
from datetime import datetime
import os

DB_PATH = 'data/bot.db'

local_storage = threading.local()

def get_connection():
    """Get thread-local database connection"""
    if not hasattr(local_storage, 'connection') or local_storage.connection is None:
        os.makedirs('data', exist_ok=True)
        local_storage.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        local_storage.connection.row_factory = sqlite3.Row
    return local_storage.connection

def init_database():
    """Initialize database tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            credits INTEGER DEFAULT 0,
            plan TEXT DEFAULT 'Free',
            plan_expiry TEXT,
            referred_by INTEGER,
            joined_date TEXT,
            total_checked INTEGER DEFAULT 0,
            total_charged INTEGER DEFAULT 0,
            total_otp INTEGER DEFAULT 0,
            total_lowfunds INTEGER DEFAULT 0,
            total_declined INTEGER DEFAULT 0,
            total_network_error INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            description TEXT,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            amount INTEGER,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            card TEXT,
            gate TEXT,
            amount REAL,
            status TEXT,
            response TEXT,
            bin_info TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()

def create_user(user_id, username, first_name, referred_by=None):
    """Create new user if not exists"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if cursor.fetchone() is None:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, credits, plan, joined_date, referred_by)
            VALUES (?, ?, ?, ?, 'Free', ?, ?)
        ''', (user_id, username, first_name, 0, datetime.now().isoformat(), referred_by))
        conn.commit()
        return True
    return False

def get_user_credits(user_id):
    """Get user credits"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result['credits'] if result else 0

def add_credits(user_id, amount, username=None, description="Added credits"):
    """Add credits to user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    create_user(user_id, username, username)
    
    cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, user_id))
    add_transaction(user_id, amount, 'credit', description)
    conn.commit()
    return True

def deduct_credit(user_id, amount):
    """Deduct credit from user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result and result['credits'] >= amount:
        cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ?', (amount, user_id))
        add_transaction(user_id, -amount, 'debit', 'Check cost')
        conn.commit()
        return True
    return False

def transfer_credits(sender_id, receiver_id, amount):
    """Transfer credits between users"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check sender balance
    cursor.execute('SELECT credits FROM users WHERE user_id = ?', (sender_id,))
    sender = cursor.fetchone()
    if not sender or sender['credits'] < amount:
        return False, "Insufficient credits"
    
    # Deduct from sender
    cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ?', (amount, sender_id))
    add_transaction(sender_id, -amount, 'transfer_out', f'Transfer to {receiver_id}')
    
    # Add to receiver
    create_user(receiver_id, None, None)
    cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, receiver_id))
    add_transaction(receiver_id, amount, 'transfer_in', f'Transfer from {sender_id}')
    
    # Record transfer
    cursor.execute('''
        INSERT INTO transfers (sender_id, receiver_id, amount, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, receiver_id, amount, datetime.now().isoformat()))
    
    conn.commit()
    return True, "Transfer successful"

def save_card_result(user_id, card, gate, amount, status, response, bin_info):
    """Save card check result"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO card_results (user_id, card, gate, amount, status, response, bin_info, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, card, gate, amount, status, response[:200], str(bin_info), datetime.now().isoformat()))
    conn.commit()

def get_user_card_results(user_id, status_filter=None, limit=500):
    """Get user card results with optional filter"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if status_filter:
        cursor.execute('''
            SELECT * FROM card_results 
            WHERE user_id = ? AND status = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, status_filter, limit))
    else:
        cursor.execute('''
            SELECT * FROM card_results 
            WHERE user_id = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
    
    return cursor.fetchall()

def update_user_stats(user_id, stats_dict):
    """Update user statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    create_user(user_id, None, None)
    
    update_fields = []
    update_values = []
    
    for key, value in stats_dict.items():
        if key in ['total_checked', 'total_charged', 'total_otp', 
                    'total_lowfunds', 'total_declined', 'total_network_error']:
            update_fields.append(f"{key} = {key} + ?")
            update_values.append(value)
    
    if update_fields:
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = ?"
        update_values.append(user_id)
        cursor.execute(query, update_values)
        conn.commit()

def get_user_stats(user_id):
    """Get user statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT total_checked, total_charged, total_otp, 
               total_lowfunds, total_declined, total_network_error
        FROM users WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    if result:
        return {
            'total_checked': result['total_checked'],
            'total_charged': result['total_charged'],
            'total_otp': result['total_otp'],
            'total_lowfunds': result['total_lowfunds'],
            'total_declined': result['total_declined'],
            'total_network_error': result['total_network_error']
        }
    return {
        'total_checked': 0, 'total_charged': 0, 'total_otp': 0,
        'total_lowfunds': 0, 'total_declined': 0, 'total_network_error': 0
    }

def add_transaction(user_id, amount, trans_type, description):
    """Add transaction record"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, amount, trans_type, description, datetime.now().isoformat()))
    conn.commit()

def get_all_users():
    """Get all users for admin"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY credits DESC')
    return cursor.fetchall()

def get_user_transactions(user_id, limit=50):
    """Get user transactions"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM transactions 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (user_id, limit))
    return cursor.fetchall()

def get_transfer_history(user_id, limit=50):
    """Get transfer history for user"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM transfers 
        WHERE sender_id = ? OR receiver_id = ?
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (user_id, user_id, limit))
    return cursor.fetchall()

def get_total_stats():
    """Get total bot statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total_users FROM users')
    total_users = cursor.fetchone()['total_users']
    
    cursor.execute('SELECT SUM(credits) as total_credits FROM users')
    total_credits = cursor.fetchone()['total_credits'] or 0
    
    cursor.execute('SELECT SUM(total_checked) as total_checks FROM users')
    total_checks = cursor.fetchone()['total_checks'] or 0
    
    return {
        'total_users': total_users,
        'total_credits': total_credits,
        'total_checks': total_checks
    }

def get_user_by_username(username):
    """Find user by username"""
    conn = get_connection()
    cursor = conn.cursor()
    
    clean_username = username.replace('@', '')
    cursor.execute('SELECT * FROM users WHERE username = ?', (clean_username,))
    return cursor.fetchone()
