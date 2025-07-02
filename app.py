import os, re, csv, io, time, random, secrets
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

def generate_otp():
    """Generate a 6-digit OTP"""
    return str(random.randint(100000, 999999))

def send_otp(phone_number, otp):
    """Send OTP via Twilio SMS"""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=f"Your CampusBuzz verification code is: {otp}. Valid for 60 seconds.",
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return True, message.sid
    except Exception as e:
        print(f"Error sending OTP: {str(e)}")
        return False, str(e)
    
@app.route('/send-otp', methods=['POST'])
def send_otp_route():
    data = request.get_json()
    phone_number = data.get('phone_number')
    usertype = data.get('usertype', 'student')  # default to student if not provided

    # Basic phone number format validation
    if not phone_number or not re.match(r'^\+?[1-9]\d{9,14}$', phone_number):
        return jsonify({
            'success': False,
            'message': 'Invalid phone number format. Please include country code (e.g., +91).'
        })

    # Check if phone number already exists in DB
    if usertype == 'student':
        user = db.session.execute(
            text("SELECT id FROM student WHERE phone_number = :phone"),
            {"phone": phone_number}
        ).mappings().first()
        if user:
            return jsonify({
                'success': False,
                'message': 'This phone number is already registered as a student. Please use a different number.'
            })
    elif usertype == 'host':
        user = db.session.execute(
            text("SELECT id FROM host WHERE phone_number = :phone"),
            {"phone": phone_number}
        ).mappings().first()
        if user:
            return jsonify({
                'success': False,
                'message': 'This phone number is already registered as a host. Please use a different number.'
            })

    # Generate 6-digit OTP
    otp = generate_otp()

    # Store in session with expiry
    session['otp'] = otp
    session['otp_phone'] = phone_number
    session['otp_usertype'] = usertype
    session['otp_expires'] = (datetime.now() + timedelta(seconds=60)).timestamp()

    # DEBUG mode behavior
    if app.debug:
        print(f"DEBUG - OTP for {phone_number} ({usertype}): {otp}")
        return jsonify({'success': True, 'message': 'OTP sent (debug mode).'})

    # Send using Twilio
    success, message = send_otp(phone_number, otp)
    if success:
        return jsonify({'success': True, 'message': 'OTP sent successfully'})
    else:
        return jsonify({'success': False, 'message': f'Failed to send OTP: {message}'})

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    user_otp = data.get('otp')
    
    stored_otp = session.get('otp')
    otp_expires = session.get('otp_expires')
    
    if not stored_otp:
        return jsonify({'success': False, 'message': 'OTP session expired, please request a new OTP'})
    
    # Check if OTP has expired
    if datetime.now().timestamp() > otp_expires:
        # Clear expired OTP from session
        session.pop('otp', None)
        session.pop('otp_expires', None)
        return jsonify({'success': False, 'message': 'OTP has expired, please request a new OTP'})
    
    if user_otp == stored_otp:
        session['verified_phone'] = session.get('otp_phone')
        return jsonify({'success': True, 'message': 'Phone number verified successfully'})
    else:
        return jsonify({'success': False, 'message': 'Invalid OTP, please try again'})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        usertype = request.form['usertype']
        phone_number = request.form['phone_number']

        if session.get('verified_phone') != phone_number:
            flash('Phone number not verified. Please verify your phone number with OTP.', 'error')
            return redirect(url_for('login'))

        password = request.form['password']
        confirm_password = request.form.get('confirm-password', '')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('login'))

        if usertype == 'student':
            name = request.form['name']
            email = request.form['email']
            roll_number = request.form['roll_number']
            department = request.form['department']
            password_hash = generate_password_hash(password)

            if not re.match(r'^4MC\d{2}[A-Z]{2}\d{3}$', roll_number):
                flash('Invalid roll number format. Expected format: 4MCxxYYzzz', 'error')
                return redirect(url_for('login'))

            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                flash('Invalid email format.', 'error')
                return redirect(url_for('login'))

            try:
                existing = db.session.execute(
                    text("SELECT * FROM student WHERE roll_number = :roll OR email = :email"),
                    {"roll": roll_number, "email": email}
                ).mappings().first()

                if existing:
                    flash('Roll number or email already registered.', 'error')
                    return redirect(url_for('login'))

                db.session.execute(text("""
                    INSERT INTO student (name, email, roll_number, department, phone_number, password)
                    VALUES (:name, :email, :roll, :dept, :phone, :pwd)
                """), {
                    "name": name, "email": email, "roll": roll_number, "dept": department,
                    "phone": phone_number, "pwd": password_hash
                })
                db.session.commit()

                flash(f"Student account created successfully for {name}", 'success')
            except Exception as e:
                db.session.rollback()
                flash(f"Registration failed: {str(e)}", 'error')

        elif usertype == 'host':
            name = request.form['name']
            email = request.form['email']
            designation = request.form['designation']
            department_club = request.form['department_club']
            secret_key = request.form.get('secret_key', '')
            password_hash = generate_password_hash(password)

            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                flash('Invalid email format.', 'error')
                return redirect(url_for('login'))

            if secret_key != HOST_SECRET_KEY:
                flash('Invalid host secret key.', 'error')
                return redirect(url_for('login'))

            try:
                existing = db.session.execute(
                    text("SELECT * FROM host WHERE email = :email"),
                    {"email": email}
                ).mappings().first()

                if existing:
                    flash('Email already registered as host.', 'error')
                    return redirect(url_for('login'))

                db.session.execute(text("""
                    INSERT INTO host (name, email, designation, department_club, phone_number, password)
                    VALUES (:name, :email, :designation, :dept_club, :phone, :pwd)
                """), {
                    "name": name, "email": email, "designation": designation,
                    "dept_club": department_club, "phone": phone_number, "pwd": password_hash
                })
                db.session.commit()

                flash(f"Host account created successfully for {name}", 'success')
            except Exception as e:
                db.session.rollback()
                flash(f"Host registration failed: {str(e)}", 'error')

        # Clear OTP session
        for key in ['otp', 'otp_phone', 'otp_expires', 'verified_phone']:
            session.pop(key, None)

        return redirect(url_for('login'))
# Replace your existing forgot password routes with these SQLAlchemy versions

@app.route('/request-reset-otp', methods=['POST'])
def request_reset_otp():
    data = request.get_json()
    identifier = data.get('identifier')
    usertype = data.get('usertype')
    secret_key = data.get('secret_key', '')
    
    # Validate inputs
    if not identifier or not usertype:
        return jsonify({'success': False, 'message': 'Missing required information'})
    
    # For host users, validate secret key
    if usertype == 'host' and secret_key != HOST_SECRET_KEY:
        return jsonify({'success': False, 'message': 'Invalid host secret key'})
    
    try:
        # Find user in database using SQLAlchemy
        if usertype == 'student':
            user = db.session.execute(
                text('SELECT * FROM student WHERE roll_number = :identifier'),
                {'identifier': identifier}
            ).mappings().first()
        else:  # host
            user = db.session.execute(
                text('SELECT * FROM host WHERE email = :identifier'),
                {'identifier': identifier}
            ).mappings().first()
            
        if not user:
            return jsonify({'success': False, 'message': f'No {usertype} account found with the provided details'})
        
        # Get the user's phone number
        phone_number = user.get('phone_number')
        
        if not phone_number:
            return jsonify({'success': False, 'message': 'No phone number associated with this account'})
        
        # Generate OTP
        otp = generate_otp()
        
        # Store reset OTP in session
        session['reset_otp'] = otp
        session['reset_phone'] = phone_number
        session['reset_identifier'] = identifier
        session['reset_usertype'] = usertype
        session['reset_otp_expires'] = (datetime.now() + timedelta(seconds=60)).timestamp()
        
        # In development mode, print OTP to console instead of sending
        if app.debug:
            print(f"DEBUG - Reset OTP for {identifier} ({usertype}): {otp}")
            return jsonify({'success': True, 'message': 'OTP sent successfully (check console in debug mode)'})
        
        # Send OTP via Twilio in production
        success, message = send_otp(phone_number, otp)
        
        if success:
            return jsonify({'success': True, 'message': 'OTP sent successfully'})
        else:
            return jsonify({'success': False, 'message': f'Failed to send OTP: {message}'})
            
    except Exception as e:
        print(f"Error in request-reset-otp: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while processing your request'})

@app.route('/verify-reset-otp', methods=['POST'])
def verify_reset_otp():
    data = request.get_json()
    user_otp = data.get('otp')
    
    # Validate session data
    stored_otp = session.get('reset_otp')
    stored_identifier = session.get('reset_identifier')
    stored_usertype = session.get('reset_usertype')
    otp_expires = session.get('reset_otp_expires')
    
    if not stored_otp or not stored_identifier or not stored_usertype:
        return jsonify({'success': False, 'message': 'Reset session expired, please start over'})
    
    # Check if OTP has expired
    if datetime.now().timestamp() > otp_expires:
        # Clear expired session data
        for key in ['reset_otp', 'reset_phone', 'reset_identifier', 'reset_usertype', 'reset_otp_expires']:
            session.pop(key, None)
        return jsonify({'success': False, 'message': 'OTP has expired, please request a new one'})
    
    # Verify OTP
    if user_otp == stored_otp:
        # Store verification status in session
        session['reset_verified'] = True
        return jsonify({'success': True, 'message': 'OTP verified successfully'})
    else:
        return jsonify({'success': False, 'message': 'Invalid OTP, please try again'})

@app.route('/reset-password', methods=['POST'])
def reset_password():
    # Check if user has verified OTP
    if not session.get('reset_verified'):
        return jsonify({'success': False, 'message': 'Please verify your OTP first'})
    
    data = request.get_json()
    identifier = data.get('identifier')
    usertype = data.get('usertype')
    new_password = data.get('new_password')
    
    # Validate inputs
    if not identifier or not usertype or not new_password:
        return jsonify({'success': False, 'message': 'Missing required information'})
    
    # Verify identifier and usertype match session
    if identifier != session.get('reset_identifier') or usertype != session.get('reset_usertype'):
        return jsonify({'success': False, 'message': 'Invalid request, please start over'})
    
    # Validate password length
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'})
    
    # Hash new password
    password_hash = generate_password_hash(new_password)
    
    try:
        # Update password in database using SQLAlchemy
        if usertype == 'student':
            result = db.session.execute(
                text('UPDATE student SET password = :password WHERE roll_number = :identifier'),
                {'password': password_hash, 'identifier': identifier}
            )
        else:  # host
            result = db.session.execute(
                text('UPDATE host SET password = :password WHERE email = :identifier'),
                {'password': password_hash, 'identifier': identifier}
            )
            
        db.session.commit()
        
        if result.rowcount == 0:
            return jsonify({'success': False, 'message': 'Failed to update password'})
        
        # Clear reset session data
        for key in ['reset_otp', 'reset_phone', 'reset_identifier', 'reset_usertype', 'reset_otp_expires', 'reset_verified']:
            session.pop(key, None)
        
        return jsonify({'success': True, 'message': 'Password updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in reset-password: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while resetting your password'})
    
@app.route('/create_event', methods=['POST'])
def create_event():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to create events', 'error')
        return redirect(url_for('login'))

    # Get form data
    title = request.form['title']
    description = request.form['description']
    date = request.form['date']
    time_str = request.form['time']
    venue = request.form['venue']
    capacity = request.form['capacity']
    event_type = request.form['event_type']
    registration_deadline = request.form['registration_deadline']

    try:
        event_date_obj = datetime.strptime(date, "%Y-%m-%d")
        registration_deadline_obj = datetime.strptime(registration_deadline, "%Y-%m-%dT%H:%M")
        event_end_of_day = datetime.combine(event_date_obj, datetime.max.time())

        if registration_deadline_obj > event_end_of_day:
            flash('Registration deadline must be on or before the event day.', 'error')
            return redirect(url_for('host_dashboard'))

    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('host_dashboard'))

    # Validate image upload
    if 'event_image' not in request.files or request.files['event_image'].filename == '':
        flash('Event poster is required. Please upload an event image.', 'error')
        return redirect(url_for('host_dashboard'))

    file = request.files['event_image']
    if not allowed_file(file.filename):
        flash('Invalid image format. Allowed formats are: png, jpg, jpeg, gif.', 'error')
        return redirect(url_for('host_dashboard'))

    filename = f"event_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'event_images', filename)
    file.save(filepath)
    image_url = f"uploads/event_images/{filename}"

    # Save to database using SQLAlchemy
    try:
        db.session.execute(text('''
            INSERT INTO events (host_id, title, description, date, time, venue, capacity, 
                                event_type, image_url, registration_deadline)
            VALUES (:host_id, :title, :desc, :date, :time, :venue, :capacity, 
                    :etype, :img_url, :deadline)
        '''), {
            "host_id": session['user_id'],
            "title": title,
            "desc": description,
            "date": date,
            "time": time_str,
            "venue": venue,
            "capacity": capacity,
            "etype": event_type,
            "img_url": image_url,
            "deadline": registration_deadline
        })
        db.session.commit()
        flash('Event created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to create event: {str(e)}", 'error')

    return redirect(url_for('host_dashboard'))

@app.route('/get_event_registrations/<int:event_id>')
def get_event_registrations(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})

    try:
        event = db.session.execute(
            text("SELECT title FROM events WHERE id = :eid AND host_id = :hid"),
            {"eid": event_id, "hid": session['user_id']}
        ).mappings().first()

        if not event:
            return jsonify({'success': False, 'message': 'Event not found or unauthorized'})

        registrations = db.session.execute(text('''
            SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
                   COALESCE(er.registration_date, NOW()) as registration_date
            FROM event_registrations er
            JOIN student s ON er.student_id = s.id
            WHERE er.event_id = :eid
            ORDER BY er.registration_date DESC
        '''), {"eid": event_id}).mappings().all()

        # Convert to list and format dates
        registration_list = []
        for reg in registrations:
            reg_dict = dict(reg)
            reg_dict['registration_date'] = reg_dict['registration_date'].strftime('%Y-%m-%d %H:%M')
            registration_list.append(reg_dict)

        return jsonify({
            'success': True,
            'event_title': event['title'],
            'registrations': registration_list
        })
        
    except Exception as e:
        print(f"Error in get_event_registrations: {str(e)}")
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'})

@app.route('/download_registrations/<int:event_id>')
def download_registrations(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to download registrations', 'error')
        return redirect(url_for('login'))

    # Verify that the host owns the event
    event = db.session.execute(text('''
        SELECT title FROM events 
        WHERE id = :eid AND host_id = :hid
    '''), {"eid": event_id, "hid": session['user_id']}).mappings().first()

    if not event:
        flash('Event not found or unauthorized', 'error')
        return redirect(url_for('host_dashboard'))

    # Fetch registrations
    registrations = db.session.execute(text('''
        SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
               er.registration_date
        FROM event_registrations er
        JOIN student s ON er.student_id = s.id
        WHERE er.event_id = :eid
        ORDER BY er.registration_date
    '''), {"eid": event_id}).mappings().all()

    # Generate CSV content
    import csv
    import io
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write CSV header
    writer.writerow(['Name', 'Roll Number', 'Email', 'Phone', 'Department', 'Registration Date'])

    # Write CSV data rows
    for reg in registrations:
        writer.writerow([
            reg['name'],
            reg['roll_number'],
            reg['email'],
            reg['phone_number'],
            reg['department'],
            reg['registration_date'].strftime('%Y-%m-%d %H:%M')
        ])

    # Return as downloadable response
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=registrations_{event_id}.csv'
        }
    )
    return response

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