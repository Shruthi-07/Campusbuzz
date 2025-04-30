import os, re, time, random, secrets
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mysqldb import MySQL
import MySQLdb.cursors
from twilio.rest import Client
from dotenv import load_dotenv
import os
from twilio.rest import Client

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
@app.template_filter('zfill')
def jinja2_zfill(value, width):
    """Pad a string with zeros to a specific width."""
    return str(value).zfill(width)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret')  # Required for session handling
HOST_SECRET_KEY = 'hostkey456'  # Used only to verify host registration/login

# File upload configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'event_images'), exist_ok=True)

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

otp_store = {}

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')

# Session timeout configuration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

mysql = MySQL(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Fetch upcoming events for display
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT e.*, h.name as host_name, h.department_club as department_club 
        FROM events e 
        JOIN host h ON e.host_id = h.id 
        WHERE e.date >= CURDATE() 
        ORDER BY e.date ASC, e.time ASC
    ''')
    events = cursor.fetchall()
    cursor.close()
    
    return render_template('index.html', logged_in='email' in session, events=events)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Existing login code remains the same
    if request.method == 'POST':
        usertype = request.form['usertype']
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        if usertype == 'student':
            cursor.execute('SELECT * FROM student WHERE roll_number = %s', (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['usertype'] = 'student'
                session['username'] = user['roll_number']
                session['name'] = user['name']
                session['email'] = user['email']
                session['user_id'] = user['id']
                return redirect(url_for('index'))
            else:
                flash('Invalid roll number or password', 'error')

        elif usertype == 'host':
            # For hosts, validate the secret key first
            host_secret_key = request.form.get('host_secret_key', '')
            if host_secret_key != HOST_SECRET_KEY:
                flash('Invalid host secret key', 'error')
                return render_template('login.html')
                
            cursor.execute('SELECT * FROM host WHERE email = %s', (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['usertype'] = 'host'
                session['username'] = user['email']
                session['name'] = user['name']
                session['email'] = user['email']
                session['user_id'] = user['id']
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
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM student WHERE id = %s', (session['user_id'],))
    student_data = cursor.fetchone()
    
    # Get active registrations (upcoming events)
    cursor.execute('''
        SELECT er.registration_date, er.event_id, 
               e.title, e.date, e.time, e.venue, e.event_type, e.image_url,
               h.name as host_name, h.department_club
        FROM event_registrations er
        JOIN events e ON er.event_id = e.id
        JOIN host h ON e.host_id = h.id
        WHERE er.student_id = %s AND e.date >= CURDATE()
        ORDER BY e.date ASC, e.time ASC
    ''', (session['user_id'],))
    active_registrations = cursor.fetchall()
    
    cursor.execute("SHOW TABLES LIKE 'student_event_history'")
    student_history_exists = cursor.fetchone()
    
    past_events = []
    if student_history_exists:
        cursor.execute('''
            SELECT * FROM student_event_history
            WHERE student_id = %s
            ORDER BY date DESC
        ''', (session['user_id'],))
        past_events = cursor.fetchall()
    
    cursor.close()
    
    return render_template(
        'student_dashboard.html', 
        student_data=student_data,
        active_registrations=active_registrations,
        past_events=past_events
    )

def cleanup_events(silent=False):
    # Move expired events to history
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    today = date.today()
    
    # Check if student_event_history table exists, if not create it
    cursor.execute("SHOW TABLES LIKE 'student_event_history'")
    if not cursor.fetchone():
        cursor.execute('''
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
        ''')
        mysql.connection.commit()
    
    # Get expired events (past events)
    cursor.execute('''
        SELECT e.*, h.name as host_name, h.department_club
        FROM events e
        JOIN host h ON e.host_id = h.id
        WHERE e.date < %s
    ''', (today,))
    
    expired_events = cursor.fetchall()
    moved_count = 0
    
    for event in expired_events:
        # First, get all student registrations for this event
        cursor.execute('''
            SELECT er.* 
            FROM event_registrations er
            WHERE er.event_id = %s
        ''', (event['id'],))
        registrations = cursor.fetchall()
        
        # Record event in history with registrations count
        cursor.execute('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, 
                capacity, registrations, event_type, image_url, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ''', (
            event['host_id'], event['title'], event['description'], 
            event['date'], event['time'], event['venue'],
            event['capacity'], len(registrations), event['event_type'], 
            event['image_url']
        ))
        
        # Add each student's registration to student_event_history
        for reg in registrations:
            cursor.execute('''
                INSERT INTO student_event_history (
                    student_id, event_id, title, date, time, venue, 
                    event_type, host_name, department_club, image_url, registration_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                reg['student_id'], event['id'], event['title'], event['date'], 
                event['time'], event['venue'], event['event_type'], 
                event['host_name'], event['department_club'], event['image_url'],
                reg['registration_date']
            ))
        
        # Delete registrations
        cursor.execute('DELETE FROM event_registrations WHERE event_id = %s', (event['id'],))
        
        # Delete the event
        cursor.execute('DELETE FROM events WHERE id = %s', (event['id'],))
        moved_count += 1
    
    mysql.connection.commit()
    cursor.close()
    
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
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if the event exists and the student is registered
    cursor.execute('''
        SELECT e.title
        FROM events e
        JOIN event_registrations er ON e.id = er.event_id
        WHERE e.id = %s AND er.student_id = %s
    ''', (event_id, session['user_id']))
    event = cursor.fetchone()
    
    if not event:
        flash('You are not registered for this event or the event does not exist', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Cancel the registration
    cursor.execute('''
        DELETE FROM event_registrations 
        WHERE event_id = %s AND student_id = %s
    ''', (event_id, session['user_id']))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Your registration for "{event["title"]}" has been cancelled', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/host_dashboard')
def host_dashboard():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return redirect(url_for('login'))
        
    # Automatically check for expired events and move them to history
    cleanup_events(silent=True)  # Add a silent parameter
        
    # Get host details
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM host WHERE id = %s', (session['user_id'],))
    host_data = cursor.fetchone()
    
    # Get active events by this host
    cursor.execute('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as registrations 
        FROM events e 
        WHERE e.host_id = %s AND e.date >= CURDATE() 
        ORDER BY e.date ASC
    ''', (session['user_id'],))
    active_events = cursor.fetchall()
    
    # Get past events by this host
    cursor.execute('''
        SELECT * FROM event_history 
        WHERE host_id = %s 
        ORDER BY date DESC
    ''', (session['user_id'],))
    past_events = cursor.fetchall()
    
    cursor.close()
    
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
    usertype = data.get('usertype', 'student')  # Get usertype from request
    
    # Validate phone number format (basic validation)
    if not phone_number or not re.match(r'^\+?[1-9]\d{9,14}$', phone_number):
        return jsonify({
            'success': False, 
            'message': 'Invalid phone number format. Please include country code (e.g., +91).'
        })
    
    # Check if phone number already exists in the same usertype's table
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if usertype == 'student':
        cursor.execute('SELECT * FROM student WHERE phone_number = %s', (phone_number,))
        user = cursor.fetchone()
        if user:
            return jsonify({
                'success': False, 
                'message': 'This phone number is already registered as a student. Please use a different number.'
            })
    elif usertype == 'host':
        cursor.execute('SELECT * FROM host WHERE phone_number = %s', (phone_number,))
        user = cursor.fetchone()
        if user:
            return jsonify({
                'success': False, 
                'message': 'This phone number is already registered as a host. Please use a different number.'
            })
    
    # Generate OTP
    otp = generate_otp()
    
    # Store OTP in session temporarily with expiration time
    session['otp'] = otp
    session['otp_phone'] = phone_number
    session['otp_usertype'] = usertype  # Store usertype in session
    session['otp_expires'] = (datetime.now() + timedelta(seconds=60)).timestamp()
    
    # In development mode, print OTP to console
    if app.debug:
        print(f"DEBUG - OTP for {phone_number} ({usertype}): {otp}")
        return jsonify({'success': True, 'message': 'OTP sent successfully (check console in debug mode)'})
    
    # Send OTP via Twilio in production
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
        
        # Check if phone number has been verified
        if session.get('verified_phone') != phone_number:
            flash('Phone number not verified. Please verify your phone number with OTP.', 'error')
            return redirect(url_for('login'))

        # Handle password mismatch
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

            # Validate roll number
            pattern = r'^4MC\d{2}[A-Z]{2}\d{3}$'
            if not re.match(pattern, roll_number):
                flash('Invalid roll number format. Expected format: 4MCxxYYzzz', 'error')
                return redirect(url_for('login'))

            # Validate email format
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                flash('Invalid email format.', 'error')
                return redirect(url_for('login'))

            cursor = mysql.connection.cursor()
            try:
                # Check if roll number already exists
                check_cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
                check_cursor.execute('SELECT * FROM student WHERE roll_number = %s', (roll_number,))
                if check_cursor.fetchone():
                    flash('Roll number already registered.', 'error')
                    return redirect(url_for('login'))
                
                # Check if email already exists
                check_cursor.execute('SELECT * FROM student WHERE email = %s', (email,))
                if check_cursor.fetchone():
                    flash('Email already registered.', 'error')
                    return redirect(url_for('login'))
                
                cursor.execute("INSERT INTO student (name, email, roll_number, department, phone_number, password) VALUES (%s, %s, %s, %s, %s, %s)",
                               (name, email, roll_number, department, phone_number, password_hash))
                mysql.connection.commit()
                
                # Prepare success message with all details
                success_message = f"""
                Student account created successfully!
                
                Details:
                Name: {name}
                Email: {email}
                Roll Number: {roll_number}
                Department: {department}
                Phone: {phone_number}
                """
                
                flash(success_message, 'success')
                
                # Clear OTP verification session data
                session.pop('otp', None)
                session.pop('otp_phone', None)
                session.pop('otp_expires', None)
                session.pop('verified_phone', None)
                
            except Exception as e:
                flash(f'Registration failed: {str(e)}', 'error')
                print(f"ERROR: {str(e)}")
            finally:
                cursor.close()

        elif usertype == 'host':
            name = request.form['name']
            email = request.form['email']
            designation = request.form['designation']
            department_club = request.form['department_club'] 
            password_hash = generate_password_hash(password)
            secret_key = request.form.get('secret_key', '')

            # Validate email format
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                flash('Invalid email format.', 'error')
                return redirect(url_for('login'))

            # Validate secret key
            if secret_key != HOST_SECRET_KEY:
                flash('Invalid host secret key.', 'error')
                return redirect(url_for('login'))

            cursor = mysql.connection.cursor()
            try:
                # Check if email already exists
                check_cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
                check_cursor.execute('SELECT * FROM host WHERE email = %s', (email,))
                if check_cursor.fetchone():
                    flash('Email already registered.', 'error')
                    return redirect(url_for('login'))
                
                cursor.execute("INSERT INTO host (name, email, designation, department_club, phone_number, password) VALUES (%s, %s, %s, %s, %s, %s)",
                               (name, email, designation, department_club, phone_number, password_hash))
                mysql.connection.commit()
                
                # Prepare success message with all details
                success_message = f"""
                Host account created successfully!
                
                Details:
                Name: {name}
                Email: {email}
                Designation: {designation}
                Department/Club: {department_club}
                Phone: {phone_number}
                """
                
                flash(success_message, 'success')
                
                # Clear OTP verification session data
                session.pop('otp', None)
                session.pop('otp_phone', None)
                session.pop('otp_expires', None)
                session.pop('verified_phone', None)
                
            except Exception as e:
                flash(f'Host registration failed: {str(e)}', 'error')
                print(f"ERROR: {str(e)}")
            finally:
                cursor.close()

        return redirect(url_for('login'))

@app.route('/create_event', methods=['POST'])
def create_event():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to create events', 'error')
        return redirect(url_for('login'))
    
    # Get form data
    title = request.form['title']
    description = request.form['description']
    date = request.form['date']
    time = request.form['time']
    venue = request.form['venue']
    capacity = request.form['capacity']
    event_type = request.form['event_type']
    registration_deadline = request.form['registration_deadline']
    
    try:
        # Parse event date and registration deadline properly
        event_date_obj = datetime.strptime(date, "%Y-%m-%d")
        registration_deadline_obj = datetime.strptime(registration_deadline, "%Y-%m-%dT%H:%M")

        # Create "event end of day" time
        event_end_of_day = datetime.combine(event_date_obj, datetime.max.time())

        # Compare
        if registration_deadline_obj > event_end_of_day:
            flash('Registration deadline must be on or before the event day.', 'error')
            return redirect(url_for('host_dashboard'))

    except ValueError as ve:
        flash('Invalid date format.', 'error')
        return redirect(url_for('host_dashboard'))

    # Handle mandatory image upload
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

    # Save to database
    cursor = mysql.connection.cursor()
    cursor.execute('''
        INSERT INTO events (host_id, title, description, date, time, venue, capacity, 
                         event_type, image_url, registration_deadline) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        session['user_id'], title, description, date, time, venue, capacity,
        event_type, image_url, registration_deadline
    ))
    mysql.connection.commit()
    cursor.close()
    
    flash('Event created successfully!', 'success')
    return redirect(url_for('host_dashboard'))

@app.route('/get_event_registrations/<int:event_id>')
def get_event_registrations(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    # Verify this host owns the event
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT title FROM events WHERE id = %s AND host_id = %s', 
                  (event_id, session['user_id']))
    event = cursor.fetchone()
    
    if not event:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})
    
    # Get registrations
    cursor.execute('''
        SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
               er.registration_date
        FROM event_registrations er
        JOIN student s ON er.student_id = s.id
        WHERE er.event_id = %s
        ORDER BY er.registration_date
    ''', (event_id,))
    registrations = cursor.fetchall()
    cursor.close()
    
    # Format dates for display
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
    
    # Verify this host owns the event
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT title FROM events WHERE id = %s AND host_id = %s', 
                  (event_id, session['user_id']))
    event = cursor.fetchone()
    
    if not event:
        flash('Event not found or unauthorized', 'error')
        return redirect(url_for('host_dashboard'))
    
    # Get registrations
    cursor.execute('''
        SELECT s.name, s.roll_number, s.email, s.phone_number, s.department, 
               er.registration_date
        FROM event_registrations er
        JOIN student s ON er.student_id = s.id
        WHERE er.event_id = %s
        ORDER BY er.registration_date
    ''', (event_id,))
    registrations = cursor.fetchall()
    cursor.close()
    
    # Generate CSV content
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Name', 'Roll Number', 'Email', 'Phone', 'Department', 'Registration Date'])
    
    # Write data
    for reg in registrations:
        writer.writerow([
            reg['name'],
            reg['roll_number'],
            reg['email'],
            reg['phone_number'],
            reg['department'],
            reg['registration_date'].strftime('%Y-%m-%d %H:%M')
        ])
    
    # Convert to response
    from flask import Response
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
    
    # Verify this host owns the event
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM events WHERE id = %s AND host_id = %s', 
                  (event_id, session['user_id']))
    event = cursor.fetchone()
    
    if not event:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})
    
    # Count registrations
    cursor.execute('SELECT COUNT(*) as reg_count FROM event_registrations WHERE event_id = %s', (event_id,))
    reg_count = cursor.fetchone()['reg_count']
    
    # Delete event registrations
    cursor.execute('DELETE FROM event_registrations WHERE event_id = %s', (event_id,))
    
    # Add to event history
    cursor.execute('''
        INSERT INTO event_history (host_id, title, description, date, time, venue, capacity, 
                               registrations, event_type, image_url, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ''', (
        session['user_id'], event['title'], event['description'], event['date'], 
        event['time'], event['venue'], event['capacity'], reg_count,
        event['event_type'], event['image_url']
    ))
    
    # Delete event
    cursor.execute('DELETE FROM events WHERE id = %s', (event_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True, 'message': 'Event cancelled successfully'})

@app.route('/event_report/<int:event_id>')
def event_report(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        flash('You must be logged in as a host to view reports', 'error')
        return redirect(url_for('login'))
    
    # Get event details from history
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM event_history WHERE id = %s AND host_id = %s', 
                  (event_id, session['user_id']))
    event = cursor.fetchone()
    cursor.close()
    
    if not event:
        flash('Event not found or unauthorized', 'error')
        return redirect(url_for('host_dashboard'))
    
    return render_template('event_report.html', event=event)

@app.route('/delete_past_event/<int:event_id>', methods=['POST'])
def delete_past_event(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    # Verify this host owns the event
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM event_history WHERE id = %s AND host_id = %s', 
                  (event_id, session['user_id']))
    event = cursor.fetchone()
    
    if not event:
        return jsonify({'success': False, 'message': 'Event not found or unauthorized'})
    
    # Delete the event from history
    cursor.execute('DELETE FROM event_history WHERE id = %s', (event_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True, 'message': 'Event record deleted successfully'})

@app.route('/check_expired_events')
def check_expired_events():
    if 'loggedin' not in session or session.get('usertype') != 'host':
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get expired events
    cursor.execute('''
        SELECT e.*, (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as reg_count
        FROM events e
        WHERE e.date < CURDATE() 
    ''')
    expired_events = cursor.fetchall()
    
    # Move to history
    for event in expired_events:
        # Add to history
        cursor.execute('''
            INSERT INTO event_history (host_id, title, description, date, time, venue, 
                                   capacity, registrations, event_type, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            event['host_id'], event['title'], event['description'], event['date'], 
            event['time'], event['venue'], event['capacity'], event['reg_count'],
            event['event_type'], event['image_url']
        ))
        
        # Delete registrations
        cursor.execute('DELETE FROM event_registrations WHERE event_id = %s', (event['id'],))
        
        # Delete event
        cursor.execute('DELETE FROM events WHERE id = %s', (event['id'],))
    
    mysql.connection.commit()
    cursor.close()
    
    return jsonify({'success': True, 'count': len(expired_events)})

# Route to handle student event registration
@app.route('/register_for_event/<int:event_id>', methods=['POST'])
def register_for_event(event_id):
    if 'loggedin' not in session or session.get('usertype') != 'student':
        flash('You must be logged in as a student to register for events', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if event exists and is not full
    cursor.execute('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as registrations
        FROM events e
        WHERE e.id = %s
    ''', (event_id,))
    event = cursor.fetchone()
    
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
    
    # Check if student is already registered
    cursor.execute('''
        SELECT * FROM event_registrations 
        WHERE event_id = %s AND student_id = %s
    ''', (event_id, session['user_id']))
    
    if cursor.fetchone():
        flash('You are already registered for this event', 'info')
        return redirect(url_for('index'))
    
    # Register student
    cursor.execute('''
        INSERT INTO event_registrations (event_id, student_id) 
        VALUES (%s, %s)
    ''', (event_id, session['user_id']))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Successfully registered for {event["title"]}', 'success')
    return redirect(url_for('index'))

# This should be called automatically but we'll add a manual trigger for testing
@app.route('/cleanup_events', methods=['GET'])
def cleanup_events_internal(silent=False):
    # Move expired events to history
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    today = date.today()
    
    # Get expired events (past events)
    cursor.execute('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_registrations WHERE event_id = e.id) as registrations
        FROM events e
        WHERE e.date < %s
    ''', (today,))
    
    expired_events = cursor.fetchall()
    moved_count = 0
    
    for event in expired_events:
        # Add to event history
        cursor.execute('''
            INSERT INTO event_history (
                host_id, title, description, date, time, venue, 
                capacity, registrations, event_type, image_url
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            event['host_id'], event['title'], event['description'], 
            event['date'], event['time'], event['venue'],
            event['capacity'], event['registrations'], event['event_type'], 
            event['image_url']
        ))
        
        # Delete registrations
        cursor.execute('DELETE FROM event_registrations WHERE event_id = %s', (event['id'],))
        
        # Delete the event
        cursor.execute('DELETE FROM events WHERE id = %s', (event['id'],))
        moved_count += 1
    
    mysql.connection.commit()
    cursor.close()
    
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