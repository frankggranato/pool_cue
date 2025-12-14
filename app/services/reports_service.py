"""
Brand Reports Service - Generate monthly brand decks
"""
from ..database import get_db
from . import brand_service
from . import stats_service
from . import survey_service
import json
from datetime import datetime

def generate_brand_report(brand_id, start_date, end_date):
    """Generate comprehensive brand report."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get brand info
    cursor.execute('SELECT name, category FROM brands WHERE id = ?', (brand_id,))
    brand_row = cursor.fetchone()
    if not brand_row:
        conn.close()
        return None
    
    brand_name = brand_row[0]
    brand_category = brand_row[1]
    
    # Get metrics
    metrics = brand_service.get_brand_metrics(brand_id, start_date, end_date)
    
    # Get heatmap
    heatmap = stats_service.get_activity_heatmap()
    
    # Get survey insights for this brand
    cursor.execute('''
        SELECT q.text, sr.answer_json, COUNT(*) as cnt
        FROM survey_responses sr
        JOIN survey_questions q ON sr.question_id = q.id
        WHERE q.brand_id = ? AND sr.answered_at BETWEEN ? AND ?
        GROUP BY q.id, sr.answer_json
        ORDER BY cnt DESC
    ''', (brand_id, start_date, end_date))
    survey_insights = []
    for row in cursor.fetchall():
        survey_insights.append({
            'question': row[0],
            'answer': json.loads(row[1]) if row[1] else None,
            'count': row[2]
        })
    
    # Get cohort interactions (which player types see this brand)
    cursor.execute('''
        SELECT pc.cohort_tags_json, COUNT(*) as cnt
        FROM brand_impressions bi
        JOIN player_cohorts pc ON bi.bar_id IS NOT NULL
        WHERE bi.brand_id = ? AND bi.occurred_at BETWEEN ? AND ?
        GROUP BY pc.cohort_tags_json
        ORDER BY cnt DESC LIMIT 5
    ''', (brand_id, start_date, end_date))
    top_cohorts = []
    for row in cursor.fetchall():
        tags = json.loads(row[0]) if row[0] else []
        top_cohorts.append({'tags': tags, 'impressions': row[1]})
    
    # Build summary
    summary = {
        'brand_name': brand_name,
        'brand_category': brand_category,
        'period': {'start': start_date, 'end': end_date},
        'metrics': metrics,
        'survey_insights': survey_insights[:10],
        'top_cohorts': top_cohorts,
        'recommendations': _generate_recommendations(metrics, heatmap)
    }
    
    # Save report
    cursor.execute('''INSERT INTO brand_reports (brand_id, period_start, period_end, summary_json)
                      VALUES (?, ?, ?, ?)''',
                   (brand_id, start_date, end_date, json.dumps(summary)))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {'id': report_id, 'summary': summary}

def _generate_recommendations(metrics, heatmap):
    """Generate simple text recommendations."""
    recs = []
    
    # Best times
    best_hours = []
    for h in range(24):
        total = sum(heatmap[d][h] for d in range(7))
        best_hours.append((h, total))
    best_hours.sort(key=lambda x: -x[1])
    top_hours = [h[0] for h in best_hours[:3]]
    
    hour_str = ', '.join([f"{h}:00" for h in sorted(top_hours)])
    recs.append(f"Peak activity hours: {hour_str}")
    
    # Best days
    day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    day_totals = [(d, sum(heatmap[d])) for d in range(7)]
    day_totals.sort(key=lambda x: -x[1])
    best_days = [day_names[d[0]] for d in day_totals[:3]]
    recs.append(f"Best days: {', '.join(best_days)}")
    
    # CTR recommendation
    if metrics['ctr'] < 1:
        recs.append("Consider more engaging creative to improve CTR")
    elif metrics['ctr'] > 3:
        recs.append("Strong CTR - creative resonates well with audience")
    
    # Top bars
    if metrics['top_bars']:
        bar_names = ', '.join([b['name'] for b in metrics['top_bars'][:3]])
        recs.append(f"Top performing bars: {bar_names}")
    
    return recs

def get_all_reports(brand_id=None, limit=20):
    """Get list of generated reports."""
    conn = get_db()
    cursor = conn.cursor()
    
    if brand_id:
        cursor.execute('''SELECT br.id, br.period_start, br.period_end, br.generated_at, br.summary_json, b.name
                          FROM brand_reports br
                          JOIN brands b ON br.brand_id = b.id
                          WHERE br.brand_id = ?
                          ORDER BY br.generated_at DESC LIMIT ?''', (brand_id, limit))
    else:
        cursor.execute('''SELECT br.id, br.period_start, br.period_end, br.generated_at, br.summary_json, b.name
                          FROM brand_reports br
                          JOIN brands b ON br.brand_id = b.id
                          ORDER BY br.generated_at DESC LIMIT ?''', (limit,))
    
    reports = []
    for row in cursor.fetchall():
        summary = json.loads(row[4]) if row[4] else {}
        reports.append({
            'id': row[0],
            'period_start': row[1],
            'period_end': row[2],
            'generated_at': row[3],
            'brand_name': row[5],
            'impressions': summary.get('metrics', {}).get('impressions', 0),
            'ctr': summary.get('metrics', {}).get('ctr', 0)
        })
    
    conn.close()
    return reports
