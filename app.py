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
            recurrence_day INTEGER
        )
    ''')
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
    
    # 같은 약속 + 같은 이름 참여자 찾기
    cursor.execute(
        'SELECT id FROM participants WHERE meeting_id = ? AND name = ?',
        (meeting_id, name)
    )
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({'exists': False})
    
    participant_id = row[0]
    
    # 안 되는 날짜 가져오기
    cursor.execute(
        'SELECT date, is_recurring, recurrence_day FROM unavailable_dates WHERE participant_id = ?',
        (participant_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    dates = [r[0] for r in rows if r[1] == 0]
    recurring = [r[2] for r in rows if r[1] == 1]
    
    return jsonify({
        'exists': True,
        'dates': dates,
        'recurring': recurring
    })

# 참여자 데이터 저장 (수정도 가능)
@app.route('/meeting/<meeting_id>/submit', methods=['POST'])
def submit_availability(meeting_id):
    data = request.json
    name = data.get('name')
    dates = data.get('dates', [])
    recurring = data.get('recurring', [])
    
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    # 같은 이름 있는지 확인
    cursor.execute(
        'SELECT id FROM participants WHERE meeting_id = ? AND name = ?',
        (meeting_id, name)
    )
    existing = cursor.fetchone()
    
    if existing:
        # 기존 사용자 → 기존 일정 다 지우고 새로 저장 (덮어쓰기)
        participant_id = existing[0]
        cursor.execute(
            'DELETE FROM unavailable_dates WHERE participant_id = ?',
            (participant_id,)
        )
    else:
        # 새 사용자 → 새로 추가
        cursor.execute(
            'INSERT INTO participants (meeting_id, name) VALUES (?, ?)',
            (meeting_id, name)
        )
        participant_id = cursor.lastrowid
    
    # 일회성 안 되는 날 저장
    for date in dates:
        cursor.execute(
            'INSERT INTO unavailable_dates (participant_id, date, is_recurring) VALUES (?, ?, 0)',
            (participant_id, date)
        )
    
    # 반복 요일 저장
    for day in recurring:
        cursor.execute(
            'INSERT INTO unavailable_dates (participant_id, date, is_recurring, recurrence_day) VALUES (?, ?, 1, ?)',
            (participant_id, '', day)
        )
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'updated': existing is not None})

# 결과 페이지
@app.route('/meeting/<meeting_id>/result')
def result_page(meeting_id):
    conn = sqlite3.connect('meetings.db')
    cursor = conn.cursor()
    
    # 약속 정보
    cursor.execute('SELECT title FROM meetings WHERE id = ?', (meeting_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return '<h1>약속을 찾을 수 없어 😢</h1>', 404
    title = row[0]
    
    # 참여자들
    cursor.execute('SELECT id, name FROM participants WHERE meeting_id = ?', (meeting_id,))
    participants_data = cursor.fetchall()
    participant_names = [p[1] for p in participants_data]
    
    # 각 참여자별 안 되는 날 / 반복 요일
    one_time = {}      # {이름: [날짜들]}
    recurring = {}     # {이름: [요일들]}
    
    for pid, pname in participants_data:
        cursor.execute(
            'SELECT date, is_recurring, recurrence_day FROM unavailable_dates WHERE participant_id = ?',
            (pid,)
        )
        rows = cursor.fetchall()
        one_time[pname] = [r[0] for r in rows if r[1] == 0]
        recurring[pname] = [r[2] for r in rows if r[1] == 1]
    
    conn.close()
    
    return render_template(
        'result.html',
        title=title,
        meeting_id=meeting_id,
        participants=participant_names,
        one_time=one_time,
        recurring=recurring
    )

init_db()  # 서버 시작할 때 항상 실행

if __name__ == '__main__':
    app.run(debug=True)