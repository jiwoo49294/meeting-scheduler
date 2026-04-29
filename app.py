from flask import Flask, render_template, request, jsonify
import sqlite3
import uuid

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            name TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS unavailable_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            is_recurring INTEGER DEFAULT 0,
            recurrence_day INTEGER,
            is_exception INTEGER DEFAULT 0
        )
    ''')
    
    # 이미 있는 DB에 컬럼 추가 (있으면 무시됨)
    try:
        cursor.execute('ALTER TABLE unavailable_dates ADD COLUMN is_exception INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()
    print("✅ 데이터베이스 준비 완료!")

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/create', methods=['POST'])
def create_meeting():
    title = request.form['title']
    meeting_id = str(uuid.uuid4())[:8]
    
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO meetings (id, title) VALUES (?, ?)', (meeting_id, title))
    conn.commit()
    conn.close()
    
    link = request.host_url + 'meeting/' + meeting_id
    return render_template('created.html', title=title, link=link)

# 참여 페이지
@app.route('/meeting/<meeting_id>')
def meeting_page(meeting_id):
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT title FROM meetings WHERE id = ?', (meeting_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return '<h1>약속을 찾을 수 없어 😢</h1>', 404
    
    return render_template('meeting.html', title=row[0], meeting_id=meeting_id)

# 이름으로 기존 일정 불러오기
@app.route('/meeting/<meeting_id>/load/<name>')
def load_existing(meeting_id, name):
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT id FROM participants WHERE meeting_id = ? AND name = ?',
        (meeting_id, name)
    )
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({'exists': False})
    
    participant_id = row[0]
    
    cursor.execute(
        'SELECT date, is_recurring, recurrence_day, is_exception FROM unavailable_dates WHERE participant_id = ?',
        (participant_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    # 일회성 안 되는 날
    dates = [r[0] for r in rows if r[1] == 0 and r[3] == 0]
    # 반복 요일
    recurring = [r[2] for r in rows if r[1] == 1]
    # 예외 (반복이지만 이번엔 됨)
    exceptions = [r[0] for r in rows if r[1] == 0 and r[3] == 1]
    
    return jsonify({
        'exists': True,
        'dates': dates,
        'recurring': recurring,
        'exceptions': exceptions
    })

# 참여자 데이터 저장 (수정도 가능)
@app.route('/meeting/<meeting_id>/submit', methods=['POST'])
def submit_availability(meeting_id):
    data = request.json
    name = data.get('name')
    dates = data.get('dates', [])
    recurring = data.get('recurring', [])
    exceptions = data.get('exceptions', [])
    
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT id FROM participants WHERE meeting_id = ? AND name = ?',
        (meeting_id, name)
    )
    existing = cursor.fetchone()
    
    if existing:
        participant_id = existing[0]
        cursor.execute(
            'DELETE FROM unavailable_dates WHERE participant_id = ?',
            (participant_id,)
        )
    else:
        cursor.execute(
            'INSERT INTO participants (meeting_id, name) VALUES (?, ?)',
            (meeting_id, name)
        )
        participant_id = cursor.lastrowid
    
    # 일회성 안 되는 날
    for date in dates:
        cursor.execute(
            'INSERT INTO unavailable_dates (participant_id, date, is_recurring, is_exception) VALUES (?, ?, 0, 0)',
            (participant_id, date)
        )
    
    # 반복 요일
    for day in recurring:
        cursor.execute(
            'INSERT INTO unavailable_dates (participant_id, date, is_recurring, recurrence_day, is_exception) VALUES (?, ?, 1, ?, 0)',
            (participant_id, '', day)
        )
    
    # 예외 (반복인데 이번엔 됨)
    for date in exceptions:
        cursor.execute(
            'INSERT INTO unavailable_dates (participant_id, date, is_recurring, is_exception) VALUES (?, ?, 0, 1)',
            (participant_id, date)
        )
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'updated': existing is not None})

# 결과 페이지
@app.route('/meeting/<meeting_id>/result')
def result_page(meeting_id):
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT title FROM meetings WHERE id = ?', (meeting_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return '<h1>약속을 찾을 수 없어 😢</h1>', 404
    title = row[0]
    
    cursor.execute('SELECT id, name FROM participants WHERE meeting_id = ?', (meeting_id,))
    participants_data = cursor.fetchall()
    participant_names = [p[1] for p in participants_data]
    
    one_time = {}
    recurring = {}
    exceptions = {}
    
    for pid, pname in participants_data:
        cursor.execute(
            'SELECT date, is_recurring, recurrence_day, is_exception FROM unavailable_dates WHERE participant_id = ?',
            (pid,)
        )
        rows = cursor.fetchall()
        one_time[pname] = [r[0] for r in rows if r[1] == 0 and r[3] == 0]
        recurring[pname] = [r[2] for r in rows if r[1] == 1]
        exceptions[pname] = [r[0] for r in rows if r[1] == 0 and r[3] == 1]
    
    conn.close()
    
    return render_template(
        'result.html',
        title=title,
        meeting_id=meeting_id,
        participants=participant_names,
        one_time=one_time,
        recurring=recurring,
        exceptions=exceptions
    )

init_db()  # 서버 시작할 때 항상 실행

if __name__ == '__main__':
    app.run(debug=True)