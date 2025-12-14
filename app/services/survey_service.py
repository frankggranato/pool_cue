"""
Survey Service - Manage surveys and responses
"""
from ..database import get_db
from . import token_service
import json
from datetime import datetime, timedelta

def get_available_questions(user_id, limit=3):
    """Get active questions user hasn't answered recently."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get questions not answered by this user in last 7 days
    cursor.execute('''
        SELECT q.id, q.brand_id, q.text, q.response_type, q.options_json, q.token_reward,
               b.name as brand_name
        FROM survey_questions q
        LEFT JOIN brands b ON q.brand_id = b.id
        WHERE q.is_active = 1
        AND q.id NOT IN (
            SELECT question_id FROM survey_responses 
            WHERE user_id = ? AND answered_at > datetime('now', '-7 days')
        )
        ORDER BY RANDOM()
        LIMIT ?
    ''', (user_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    questions = []
    for r in rows:
        questions.append({
            'id': r[0],
            'brand_id': r[1],
            'text': r[2],
            'response_type': r[3],
            'options': json.loads(r[4]) if r[4] else None,
            'token_reward': r[5],
            'brand_name': r[6]
        })
    return questions

def submit_answer(user_id, question_id, answer, bar_id=None):
    """Submit survey answer and award tokens."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already answered
    cursor.execute('''SELECT id FROM survey_responses 
                      WHERE user_id = ? AND question_id = ? AND answered_at > datetime('now', '-7 days')''',
                   (user_id, question_id))
    if cursor.fetchone():
        conn.close()
        return {'success': False, 'error': 'Already answered recently'}
    
    # Get token reward
    cursor.execute('SELECT token_reward FROM survey_questions WHERE id = ?', (question_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {'success': False, 'error': 'Question not found'}
    
    token_reward = row[0]
    
    # Save response
    cursor.execute('''INSERT INTO survey_responses (question_id, user_id, bar_id, answer_json) 
                      VALUES (?, ?, ?, ?)''',
                   (question_id, user_id, bar_id, json.dumps(answer)))
    conn.commit()
    conn.close()
    
    # Award tokens
    new_balance = token_service.earn_tokens(user_id, token_reward, 'survey_answer', 
                                            {'question_id': question_id})
    
    return {'success': True, 'tokens_earned': token_reward, 'new_balance': new_balance}

def get_survey_stats(brand_id=None, question_id=None):
    """Get aggregated survey statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    if question_id:
        cursor.execute('''
            SELECT answer_json, COUNT(*) as cnt
            FROM survey_responses
            WHERE question_id = ?
            GROUP BY answer_json
        ''', (question_id,))
    elif brand_id:
        cursor.execute('''
            SELECT q.text, sr.answer_json, COUNT(*) as cnt
            FROM survey_responses sr
            JOIN survey_questions q ON sr.question_id = q.id
            WHERE q.brand_id = ?
            GROUP BY q.id, sr.answer_json
        ''', (brand_id,))
    else:
        return None
    
    rows = cursor.fetchall()
    conn.close()
    return rows
