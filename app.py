import os, re, time, random, secrets
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from dotenv import load_dotenv
from twilio.rest import Client
import pymysql
pymysql.install_as_MySQLdb()

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret')
HOST_SECRET_KEY = 'hostkey456'

# File upload config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'event_images'), exist_ok=True)

# Twilio config
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
otp_store = {}

# DB config (SQLAlchemy)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}@"
    f"{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DB')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)

@app.template_filter('zfill')
def jinja2_zfill(value, width):
    return str(value).zfill(width)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    try:
        result = db.session.execute(text('''
            SELECT e.*, h.name as host_name, h.department_club as department_club 
            FROM events e 
            JOIN host h ON e.host_id = h.id 
            WHERE e.date >= CURDATE() 
            ORDER BY e.date ASC, e.time ASC
        '''))
        events = result.mappings().all()
    except Exception as e:
        print("Database error:", e)
        events = []

    return render_template('index.html', logged_in='email' in session, events=events)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usertype = request.form['usertype']
        username = request.form['username']
        password = request.form['password']

        if usertype == 'student':
            query = text("SELECT * FROM student WHERE roll_number = :roll_number")
            result = db.session.execute(query, {"roll_number": username}).mappings().first()
            if result and check_password_hash(result['password'], password):
                session['loggedin'] = True
                session['usertype'] = 'student'
                session['username'] = result['roll_number']
                session['name'] = result['name']
                session['email'] = result['email']
                session['user_id'] = result['id']
                return redirect(url_for('index'))
            else:
                flash('Invalid roll number or password', 'error')

        elif usertype == 'host':
            host_secret_key = request.form.get('host_secret_key', '')
            if host_secret_key != HOST_SECRET_KEY:
                flash('Invalid host secret key', 'error')
                return render_template('login.html')

            query = text("SELECT * FROM host WHERE email = :email")
            result = db.session.execute(query, {"email": username}).mappings().first()
            if result and check_password_hash(result['password'], password):
                session['loggedin'] = True
                session['usertype'] = 'host'
                session['username'] = result['email']
                session['name'] = result['name']
                session['email'] = result['email']
                session['user_id'] = result['id']
                return redirect(url_for('host_dashboard'))
            else:
                flash('Invalid email or password', 'error')
        else:
            flash('Invalid user type selected', 'error')

    return render_template('login.html')

@app.route('/student_dashboard')
def student_dashboard():
    if 'loggedin' not in session or session.get('usertype') != 'student':
        return redirect(url_for('login'))

    # Get student details
    student_query = text("SELECT * FROM student WHERE id = :id")
    student_data = db.session.execute(student_query, {"id": session['user_id']}).mappings().first()

    # Get active registrations
    active_query = text('''
        SELECT er.registration_date, er.event_id, 
               e.title, e.date, e.time, e.venue, e.event_type, e.image_url,
               h.name as host_name, h.department_club
        FROM event_registrations er
        JOIN events e ON er.event_id = e.id
        JOIN host h ON e.host_id = h.id
        WHERE er.student_id = :student_id AND e.date >= CURDATE()
        ORDER BY e.date ASC, e.time ASC
    ''')
    active_registrations = db.session.execute(active_query, {"student_id": session['user_id']}).mappings().all()

    # Check if student_event_history table exists
    check_table_query = text("SHOW TABLES LIKE 'student_event_history'")
    result = db.session.execute(check_table_query).first()

    past_events = []
    if result:
        past_query = text('''
            SELECT * FROM student_event_history
            WHERE student_id = :student_id
            ORDER BY date DESC
        ''')
        past_events = db.session.execute(past_query, {"student_id": session['user_id']}).mappings().all()

    return render_template(
        'student_dashboard.html',
        student_data=student_data,
        active_registrations=active_registrations,
        past_events=past_events
    )

def cleanup_events(silent=False):
    today = date.today()

    # Create table if not exists
    check = db.session.execute(text("SHOW TABLES LIKE 'student_event_history'")).first()
    if not check:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS student_event_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                event_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                time TIME NOT NULL,
                venue VARCHAR(255) NOT NULL,
                event_type VARCHAR(100) NOT NULL,
                host_name VARCHAR(255) NOT NULL,
                department_club VARCHAR(255) NOT NULL,
                image_url VARCHAR(255),
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
            )
        '''))
        db.session.commit()

    expired_events = db.session.execute(text('''
        SELECT e.*, h.name as host_name, h.department_club
        FROM events e
        JOIN host h ON e.host_id = h.id
        WHERE e.date < :today
    '''), {"today": today}).mappings().all()

    moved_count = 0

    for event in expired_events:
        registrations = db.session.execute(text('''
            SELECT * FROM event_registrations
            WHERE event_id = :event_id
        '''), {"event_id": event['id']}).mappings().all()

        db.session.execute(text('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, 
                capacity, registrations, event_type, image_url, completed_at
            )
            VALUES (:host_id, :title, :desc, :date, :time, :venue,
                    :cap, :reg, :type, :img, NOW())
        '''), {
            "host_id": event['host_id'], "title": event['title'], "desc": event['description'],
            "date": event['date'], "time": event['time'], "venue": event['venue'],
            "cap": event['capacity'], "reg": len(registrations), "type": event['event_type'],
            "img": event['image_url']
        })

        for reg in registrations:
            db.session.execute(text('''
                INSERT INTO student_event_history (
                    student_id, event_id, title, date, time, venue, 
                    event_type, host_name, department_club, image_url, registration_date
                )
                VALUES (:sid, :eid, :title, :date, :time, :venue,
                        :etype, :hname, :dept, :img, :reg_date)
            '''), {
                "sid": reg['student_id'], "eid": event['id'], "title": event['title'],
                "date": event['date'], "time": event['time'], "venue": event['venue'],
                "etype": event['event_type'], "hname": event['host_name'],
                "dept": event['department_club'], "img": event['image_url'],
                "reg_date": reg['registration_date']
            })

        db.session.execute(text('DELETE FROM event_registrations WHERE event_id = :eid'), {"eid": event['id']})
        db.session.execute(text('DELETE FROM events WHERE id = :eid'), {"eid": event['id']})
        moved_count += 1

    db.session.commit()

    if not silent and moved_count > 0:
        flash(f'{moved_count} expired events moved to history', 'info')
    if silent:
        return None
    return redirect(url_for('host_dashboard'))

@app.route('/cancel_registration/<int:event_id>')
def cancel_registration(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'student':
        flash('You must be logged in as a student to cancel registrations', 'error')
        return redirect(url_for('login'))

    result = db.session.execute(text('''
        SELECT e.title
        FROM events e
        JOIN event_registrations er ON e.id = er.event_id
        WHERE e.id = :eid AND er.student_id = :sid
    '''), {"eid": event_id, "sid": session['user_id']}).mappings().first()

    if not result:
        flash('You are not registered for this event or the event does not exist', 'error')
        return redirect(url_for('student_dashboard'))

    db.session.execute(text('''
        DELETE FROM event_registrations 
        WHERE event_id = :eid AND student_id = :sid
    '''), {"eid": event_id, "sid": session['user_id']})

    db.session.commit()
    flash(f'Your registration for "{result["title"]}" has been cancelled', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/host_dashboard')
def host_dashboard():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return redirect(url_for('login'))

    cleanup_events(silent=True)

    host_data = db.session.execute(
        text("SELECT * FROM host WHERE id = :id"),
        {"id": session['user_id']}
    ).mappings().first()

    active_events = db.session.execute(text('''
        SELECT e.*,
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as registrations 
        FROM events e 
        WHERE e.host_id = :hid AND e.date >= CURDATE()
        ORDER BY e.date ASC
    '''), {"hid": session['user_id']}).mappings().all()

    past_events = db.session.execute(
        text("SELECT * FROM event_history WHERE host_id = :hid ORDER BY date DESC"),
        {"hid": session['user_id']}
    ).mappings().all()

    return render_template(
        'host_dashboard.html',
        host_data=host_data,
        active_events=active_events,
        past_events=past_events
    )

@app.route('/send-otp', methods=['POST'])
def send_otp_route():
    data = request.get_json()
    phone_number = data.get('phone_number')
    usertype = data.get('usertype', 'student')

    if not phone_number or not re.match(r'^\+?[1-9]\d{9,14}$', phone_number):
        return jsonify({'success': False, 'message': 'Invalid phone number format. Include country code (e.g., +91).'})

    check_query = text('SELECT * FROM student WHERE phone_number = :phone') if usertype == 'student' \
        else text('SELECT * FROM host WHERE phone_number = :phone')

    exists = db.session.execute(check_query, {"phone": phone_number}).first()
    if exists:
        return jsonify({'success': False, 'message': f'This phone number is already registered as a {usertype}.'})

    otp = generate_otp()
    session['otp'] = otp
    session['otp_phone'] = phone_number
    session['otp_usertype'] = usertype
    session['otp_expires'] = (datetime.now() + timedelta(seconds=60)).timestamp()

    if app.debug:
        print(f"DEBUG - OTP for {phone_number} ({usertype}): {otp}")
        return jsonify({'success': True, 'message': 'OTP sent (debug mode).'})

    success, message = send_otp(phone_number, otp)
    return jsonify({'success': success, 'message': 'OTP sent successfully' if success else f'Failed: {message}'})

@app.route('/get_event_registrations/<int:event_id>')
def get_event_registrations(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})

    event = db.session.execute(
        text("SELECT title FROM events WHERE id = :eid AND host_id = :hid"),
        {"eid": event_id, "hid": session['user_id']}
    ).mappings().first()

    if not event:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})

    registrations = db.session.execute(text('''
        SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
               er.registration_date
        FROM event_registrations er
        JOIN student s ON er.student_id = s.id
        WHERE er.event_id = :eid
        ORDER BY er.registration_date
    '''), {"eid": event_id}).mappings().all()

    for reg in registrations:
        reg['registration_date'] = reg['registration_date'].strftime('%Y-%m-%d %H:%M')

    return jsonify({
        'success': True,
        'event_title': event['title'],
        'registrations': registrations
    })

@app.route('/download_registrations/<int:event_id>')
def download_registrations(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to download registrations', 'error')
        return redirect(url_for('login'))

    event = db.session.execute(
        text("SELECT title FROM events WHERE id = :eid AND host_id = :hid"),
        {"eid": event_id, "hid": session['user_id']}
    ).mappings().first()

    if not event:
        flash('Event not found or unauthorized', 'error')
        return redirect(url_for('host_dashboard'))

    registrations = db.session.execute(text('''
        SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
               er.registration_date
        FROM event_registrations er
        JOIN student s ON er.student_id = s.id
        WHERE er.event_id = :eid
        ORDER BY er.registration_date
    '''), {"eid": event_id}).mappings().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Roll Number', 'Email', 'Phone', 'Department', 'Registration Date'])

    for reg in registrations:
        writer.writerow([
            reg['name'], reg['roll_number'], reg['email'], reg['phone_number'],
            reg['department'], reg['registration_date'].strftime('%Y-%m-%d %H:%M')
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=registrations_{event_id}.csv'}
    )

@app.route('/cancel_event/<int:event_id>', methods=['POST'])
def cancel_event(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})

    host_id = session['user_id']

    # Verify this host owns the event
    event_result = db.session.execute(
        text('SELECT * FROM events WHERE id = :id AND host_id = :host_id'),
        {'id': event_id, 'host_id': host_id}
    ).mappings().first()

    if not event_result:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})

    # Count registrations
    reg_result = db.session.execute(
        text('SELECT COUNT(*) AS reg_count FROM event_registrations WHERE event_id = :id'),
        {'id': event_id}
    ).mappings().first()
    reg_count = reg_result['reg_count']

    # Delete event registrations
    db.session.execute(
        text('DELETE FROM event_registrations WHERE event_id = :id'),
        {'id': event_id}
    )

    # Insert into event_history
    db.session.execute(
        text('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, capacity, 
                registrations, event_type, image_url, completed_at
            ) VALUES (
                :host_id, :title, :description, :date, :time, :venue, :capacity, 
                :registrations, :event_type, :image_url, NOW()
            )
        '''),
        {
            'host_id': host_id,
            'title': event_result['title'],
            'description': event_result['description'],
            'date': event_result['date'],
            'time': event_result['time'],
            'venue': event_result['venue'],
            'capacity': event_result['capacity'],
            'registrations': reg_count,
            'event_type': event_result['event_type'],
            'image_url': event_result['image_url']
        }
    )

    # Delete event
    db.session.execute(
        text('DELETE FROM events WHERE id = :id'),
        {'id': event_id}
    )

    db.session.commit()

    return jsonify({'success': True, 'message': 'Event cancelled successfully'})

@app.route('/event_report/<int:event_id>')
def event_report(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to view reports', 'error')
        return redirect(url_for('login'))

    result = db.session.execute(
        text('SELECT * FROM event_history WHERE id = :id AND host_id = :host_id'),
        {'id': event_id, 'host_id': session['user_id']}
    ).mappings().first()

    if not result:
        flash('Event not found or unauthorized', 'error')
        return redirect(url_for('host_dashboard'))

    return render_template('event_report.html', event=result)

@app.route('/delete_past_event/<int:event_id>', methods=['POST'])
def delete_past_event(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})

    result = db.session.execute(
        text('SELECT * FROM event_history WHERE id = :id AND host_id = :host_id'),
        {'id': event_id, 'host_id': session['user_id']}
    ).mappings().first()

    if not result:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})

    db.session.execute(
        text('DELETE FROM event_history WHERE id = :id'),
        {'id': event_id}
    )
    db.session.commit()

    return jsonify({'success': True, 'message': 'Event record deleted successfully'})

@app.route('/check_expired_events')
def check_expired_events():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})

    # Get expired events with registration count
    expired_events = db.session.execute(text('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) AS reg_count
        FROM events e
        WHERE e.date < CURDATE()
    ''')).mappings().all()

    for event in expired_events:
        # Add to event history
        db.session.execute(text('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, 
                capacity, registrations, event_type, image_url
            ) VALUES (
                :host_id, :title, :description, :date, :time, :venue, 
                :capacity, :registrations, :event_type, :image_url
            )
        '''), {
            'host_id': event['host_id'],
            'title': event['title'],
            'description': event['description'],
            'date': event['date'],
            'time': event['time'],
            'venue': event['venue'],
            'capacity': event['capacity'],
            'registrations': event['reg_count'],
            'event_type': event['event_type'],
            'image_url': event['image_url']
        })

        # Delete registrations
        db.session.execute(
            text('DELETE FROM event_registrations WHERE event_id = :event_id'),
            {'event_id': event['id']}
        )

        # Delete event
        db.session.execute(
            text('DELETE FROM events WHERE id = :event_id'),
            {'event_id': event['id']}
        )

    db.session.commit()

    return jsonify({'success': True, 'count': len(expired_events)})

# Route to handle student event registration
@app.route('/register_for_event/<int:event_id>', methods=['POST'])
def register_for_event(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'student':
        flash('You must be logged in as a student to register for events', 'error')
        return redirect(url_for('login'))

    # Check if event exists and is not full
    event = db.session.execute(text('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) AS registrations
        FROM events e
        WHERE e.id = :event_id
    '''), {'event_id': event_id}).mappings().first()

    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('index'))

    if event['registrations'] >= event['capacity']:
        flash('This event is already full', 'error')
        return redirect(url_for('index'))

    # Check if registration deadline has passed
    now = datetime.now()
    if now > event['registration_deadline']:
        flash('Registration deadline has passed', 'error')
        return redirect(url_for('index'))

    # Check if student already registered
    existing = db.session.execute(text('''
        SELECT 1 FROM event_registrations 
        WHERE event_id = :event_id AND student_id = :student_id
    '''), {'event_id': event_id, 'student_id': session['user_id']}).first()

    if existing:
        flash('You are already registered for this event', 'info')
        return redirect(url_for('index'))

    # Register the student
    db.session.execute(text('''
        INSERT INTO event_registrations (event_id, student_id) 
        VALUES (:event_id, :student_id)
    '''), {'event_id': event_id, 'student_id': session['user_id']})

    db.session.commit()

    flash(f'Successfully registered for {event["title"]}', 'success')
    return redirect(url_for('index'))


# This should be called automatically but we'll add a manual trigger for testing
@app.route('/cleanup_events', methods=['GET'])
def cleanup_events_internal(silent=False):
    today = date.today()
    
    # Get expired events
    expired_events = db.session.execute(text('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as registrations
        FROM events e
        WHERE e.date < :today
    '''), {'today': today}).mappings().all()

    moved_count = 0

    for event in expired_events:
        # Insert into event_history
        db.session.execute(text('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, 
                capacity, registrations, event_type, image_url
            )
            VALUES (
                :host_id, :title, :description, :date, :time, :venue,
                :capacity, :registrations, :event_type, :image_url
            )
        '''), {
            'host_id': event['host_id'],
            'title': event['title'],
            'description': event['description'],
            'date': event['date'],
            'time': event['time'],
            'venue': event['venue'],
            'capacity': event['capacity'],
            'registrations': event['registrations'],
            'event_type': event['event_type'],
            'image_url': event['image_url']
        })

        # Delete registrations
        db.session.execute(text('DELETE FROM event_registrations WHERE event_id = :eid'), {'eid': event['id']})

        # Delete the event
        db.session.execute(text('DELETE FROM events WHERE id = :eid'), {'eid': event['id']})

        moved_count += 1

    db.session.commit()

    if not silent and moved_count > 0:
        flash(f'{moved_count} expired events moved to history', 'info')

    if silent:
        return None
    return redirect(url_for('host_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

# flask run --host=0.0.0.0 