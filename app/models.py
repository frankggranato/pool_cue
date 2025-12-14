from datetime import datetime
import secrets
from .database import get_db, log_action, mark_action_undone, get_last_removal, start_game_timer, end_game_timer, record_game, determine_match_ranked_status
from .tokens import award_game_result, TOKENS_WIN, TOKENS_LOSE

class Player:
    @staticmethod
    def find_or_create(nickname, phone=None, bar_id=None):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE LOWER(nickname) = LOWER(?)', (nickname,))
        player = cursor.fetchone()
        
        if player:
            player_id = player['id']
        else:
            cursor.execute('INSERT INTO players (nickname, phone) VALUES (?, ?)', (nickname, phone))
            conn.commit()
            player_id = cursor.lastrowid
        
        cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
        result = cursor.fetchone()
        conn.close()
        
        player_dict = dict(result) if result else None
        
        # Log queue usage for auto-invite tracking if phone provided
        if player_dict and phone and bar_id:
            from .database import log_queue_usage
            has_account = player_dict.get('account_id') is not None
            log_queue_usage(
                phone_number=phone,
                bar_id=bar_id,
                player_id=player_dict['id'],
                nickname=nickname,
                has_account=has_account
            )
        
        return player_dict
    
    @staticmethod
    def get_by_id(player_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
        player = cursor.fetchone()
        conn.close()
        return dict(player) if player else None
    
    @staticmethod
    def update_stats(player_id, won):
        conn = get_db()
        cursor = conn.cursor()
        if won:
            cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (player_id,))
        else:
            cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (player_id,))
        conn.commit()
        conn.close()


class Queue:
    @staticmethod
    def get_all():
        """Get all players in queue order."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT q.*, p.nickname FROM queue q 
            JOIN players p ON q.player_id = p.id 
            WHERE q.status IN ('waiting', 'playing')
            ORDER BY q.position ASC
        ''')
        results = cursor.fetchall()
        conn.close()
        return [dict(r) for r in results]
    
    @staticmethod
    def get_all_for_bar(bar_id):
        """Get all players in queue for a specific bar."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT q.*, p.nickname FROM queue q 
            JOIN players p ON q.player_id = p.id 
            WHERE q.status IN ('waiting', 'playing') AND q.bar_id = ?
            ORDER BY q.position ASC
        ''', (bar_id,))
        results = cursor.fetchall()
        conn.close()
        return [dict(r) for r in results]
    
    @staticmethod
    def get_by_session(session_token):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT q.*, p.nickname FROM queue q JOIN players p ON q.player_id = p.id WHERE q.session_token = ?', (session_token,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    @staticmethod
    def is_player_in_queue(player_id, bar_id=None):
        conn = get_db()
        cursor = conn.cursor()
        if bar_id:
            cursor.execute("SELECT id FROM queue WHERE player_id = ? AND bar_id = ? AND status IN ('waiting', 'playing')", (player_id, bar_id))
        else:
            cursor.execute("SELECT id FROM queue WHERE player_id = ? AND status IN ('waiting', 'playing')", (player_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None


    @staticmethod
    def add_player(player_id, partner_name=None, bar_id=None, table_id=None):
        """
        Add player to queue. If player is already in queue at this bar,
        returns existing entry instead of creating duplicate.
        Returns (queue_id, session_token).
        """
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if player already in queue at this bar (prevent duplicates)
        if bar_id:
            cursor.execute("""
                SELECT id, session_token, position 
                FROM queue 
                WHERE player_id = ? AND bar_id = ? AND status IN ('waiting', 'playing')
                ORDER BY id ASC LIMIT 1
            """, (player_id, bar_id))
        else:
            cursor.execute("""
                SELECT id, session_token, position 
                FROM queue 
                WHERE player_id = ? AND status IN ('waiting', 'playing')
                ORDER BY id ASC LIMIT 1
            """, (player_id,))
        
        existing = cursor.fetchone()
        if existing:
            # Player already in queue - return existing entry, don't duplicate
            conn.close()
            return existing['id'], existing['session_token']
        
        # Get max position for this bar
        if bar_id:
            cursor.execute('SELECT MAX(position) as max_pos FROM queue WHERE bar_id = ?', (bar_id,))
        else:
            cursor.execute('SELECT MAX(position) as max_pos FROM queue')
        row = cursor.fetchone()
        next_pos = (row['max_pos'] or 0) + 1
        
        session_token = secrets.token_urlsafe(16)
        cursor.execute('INSERT INTO queue (player_id, partner_name, position, session_token, bar_id, table_id) VALUES (?, ?, ?, ?, ?, ?)',
                       (player_id, partner_name, next_pos, session_token, bar_id, table_id))
        conn.commit()
        queue_id = cursor.lastrowid
        
        # If this is position 1 or 2, start game timer
        if next_pos <= 2:
            start_game_timer()
        
        conn.close()
        return queue_id, session_token

    @staticmethod
    def remove(queue_id, log=True):
        """Remove player from queue."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT q.*, p.nickname FROM queue q JOIN players p ON q.player_id = p.id WHERE q.id = ?', (queue_id,))
        entry = cursor.fetchone()
        
        if entry:
            if log:
                log_action('remove', player_id=entry['player_id'], player_nickname=entry['nickname'],
                           partner_name=entry['partner_name'], queue_id=queue_id, 
                           position=entry['position'], wins_on_table=entry['wins_on_table'])
            cursor.execute('DELETE FROM queue WHERE id = ?', (queue_id,))
            conn.commit()
        conn.close()
        return dict(entry) if entry else None

    @staticmethod
    def king_wins():
        """King wins - add 1 to king's wins, remove challenger."""
        queue = Queue.get_all()
        if len(queue) < 2:
            return False
        
        king = queue[0]
        challenger = queue[1]
        bar_id = king.get('bar_id', 1)
        
        # Determine if this is a ranked match
        is_ranked, ranked_source = determine_match_ranked_status(bar_id, king['id'])
        
        # Calculate game duration for anti-spam check
        game_duration = end_game_timer()
        
        # Use single connection for all operations
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            # Record game in history with ranked status and duration
            cursor.execute('''
                INSERT INTO game_history (winner_id, loser_id, bar_id, is_ranked, ranked_source, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (king['player_id'], challenger['player_id'], bar_id, 1 if is_ranked else 0, ranked_source, game_duration))
            
            # Increment king's wins
            cursor.execute('UPDATE queue SET wins_on_table = wins_on_table + 1 WHERE id = ?', (king['id'],))
            
            # Remove challenger from queue
            cursor.execute('DELETE FROM queue WHERE id = ?', (challenger['id'],))
            
            # Update player stats - king wins
            cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (king['player_id'],))
            
            # Update player stats - challenger loses
            cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (challenger['player_id'],))
            
            # Get king's current streak for bonus calculation
            cursor.execute('SELECT current_streak FROM players WHERE id = ?', (king['player_id'],))
            row = cursor.fetchone()
            king_streak = (row[0] or 0) + 1 if row else 1
            
            # Track last game result and opponent
            cursor.execute('UPDATE players SET last_opponent_id = ?, last_game_result = ? WHERE id = ?', (challenger['player_id'], 'win', king['player_id']))
            cursor.execute('UPDATE players SET last_opponent_id = ?, last_game_result = ? WHERE id = ?', (king['player_id'], 'loss', challenger['player_id']))
            
            # Update streaks - king continues/starts streak, challenger resets
            cursor.execute('UPDATE players SET current_streak = current_streak + 1 WHERE id = ?', (king['player_id'],))
            cursor.execute('UPDATE players SET best_streak = current_streak WHERE id = ? AND current_streak > best_streak', (king['player_id'],))
            cursor.execute('UPDATE players SET current_streak = 0 WHERE id = ?', (challenger['player_id'],))
            
            # Reset game timer for next game
            cursor.execute('UPDATE settings SET current_game_start = datetime("now") WHERE id = 1')
            
            # Clear ranked request from king's queue entry for next game
            cursor.execute('UPDATE queue SET ranked_request = 0, ranked_accepted = NULL, opponent_player_id = NULL WHERE id = ?', (king['id'],))
            
            conn.commit()
            
            # Award tokens using proper token service with anti-spam check
            # This is done AFTER commit so game is recorded regardless of token outcome
            award_game_result(king['player_id'], won=True, streak=king_streak, 
                            game_duration_seconds=game_duration, bar_id=bar_id)
            award_game_result(challenger['player_id'], won=False, streak=0,
                            game_duration_seconds=game_duration, bar_id=bar_id)
            
        except Exception as e:
            conn.rollback()
            print(f"King wins error: {e}")
            return False
        finally:
            conn.close()
        
        return True


    @staticmethod
    def remove_king():
        """Remove king when no challenger (reset board)."""
        queue = Queue.get_all()
        if not queue:
            return False
        king = queue[0]
        Queue.remove(king['id'])
        return True

    @staticmethod
    def challenger_wins():
        """Challenger wins - remove king, challenger becomes new king with 1 win."""
        queue = Queue.get_all()
        if len(queue) < 2:
            # No challenger - just remove king (reset board)
            return Queue.remove_king()
        
        king = queue[0]
        challenger = queue[1]
        bar_id = king.get('bar_id', 1)
        
        # Determine if this is a ranked match
        is_ranked, ranked_source = determine_match_ranked_status(bar_id, king['id'])
        
        # Calculate game duration for anti-spam check
        game_duration = end_game_timer()
        
        # Use single connection for all operations
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            # Record game in history with ranked status and duration
            cursor.execute('''
                INSERT INTO game_history (winner_id, loser_id, bar_id, is_ranked, ranked_source, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (challenger['player_id'], king['player_id'], bar_id, 1 if is_ranked else 0, ranked_source, game_duration))
            
            # Remove king from queue
            cursor.execute('DELETE FROM queue WHERE id = ?', (king['id'],))
            
            # Set challenger's wins to 1 (new king) and clear ranked request
            cursor.execute('UPDATE queue SET wins_on_table = 1, ranked_request = 0, ranked_accepted = NULL, opponent_player_id = NULL WHERE id = ?', (challenger['id'],))
            
            # Update player stats - challenger wins
            cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (challenger['player_id'],))
            
            # Update player stats - king loses
            cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (king['player_id'],))
            
            # Track last game result and opponent
            cursor.execute('UPDATE players SET last_opponent_id = ?, last_game_result = ? WHERE id = ?', (king['player_id'], 'win', challenger['player_id']))
            cursor.execute('UPDATE players SET last_opponent_id = ?, last_game_result = ? WHERE id = ?', (challenger['player_id'], 'loss', king['player_id']))
            
            # Update streaks - challenger starts streak, king resets
            cursor.execute('UPDATE players SET current_streak = 1 WHERE id = ?', (challenger['player_id'],))
            cursor.execute('UPDATE players SET best_streak = 1 WHERE id = ? AND best_streak < 1', (challenger['player_id'],))
            cursor.execute('UPDATE players SET current_streak = 0 WHERE id = ?', (king['player_id'],))
            
            # Reset game timer for next game
            cursor.execute('UPDATE settings SET current_game_start = datetime("now") WHERE id = 1')
            
            conn.commit()
            
            # Award tokens using proper token service with anti-spam check
            # Challenger is new king with streak of 1
            award_game_result(challenger['player_id'], won=True, streak=1,
                            game_duration_seconds=game_duration, bar_id=bar_id)
            award_game_result(king['player_id'], won=False, streak=0,
                            game_duration_seconds=game_duration, bar_id=bar_id)
            
        except Exception as e:
            conn.rollback()
            print(f"Challenger wins error: {e}")
            return False
        finally:
            conn.close()
        
        return True

    @staticmethod
    def undo_last_removal():
        """Undo the last player removal."""
        last = get_last_removal()
        if not last:
            return None
        
        conn = get_db()
        cursor = conn.cursor()
        session_token = secrets.token_urlsafe(16)
        cursor.execute('INSERT INTO queue (player_id, partner_name, position, wins_on_table, session_token) VALUES (?, ?, ?, ?, ?)',
                       (last['player_id'], last['partner_name'], last['position'], last['wins_on_table'] or 0, session_token))
        conn.commit()
        conn.close()
        
        mark_action_undone(last['id'])
        return last

    @staticmethod
    def leave_queue(session_token):
        entry = Queue.get_by_session(session_token)
        if entry:
            Queue.remove(entry['id'], log=False)
            return True
        return False

    @staticmethod
    def make_king(queue_id):
        """Move a player to position 1 (make them king)."""
        conn = get_db()
        cursor = conn.cursor()
        
        # Get current position of the player
        cursor.execute('SELECT position FROM queue WHERE id = ?', (queue_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        
        old_pos = row['position']
        
        # Move everyone above them down one position
        cursor.execute('UPDATE queue SET position = position + 1 WHERE position < ?', (old_pos,))
        
        # Set this player to position 1
        cursor.execute('UPDATE queue SET position = 1, wins_on_table = 0 WHERE id = ?', (queue_id,))
        
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def clear_all():
        """Clear entire queue."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM queue')
        conn.commit()
        conn.close()
        return True
