from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import jwt
from datetime import datetime, timedelta
from functools import wraps
import hashlib

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'e3c81b58bdd9a2d64fd511b3ed8a0868394c7d351e02c70fba9bdc4796a18701'

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '#Ananya19',  # Change this
    'database': 'hospital_management'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error: {e}")
        return None

# JWT Token Required Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ==================== AUTHENTICATION ====================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password', '')
    role = data.get('role')

    # Validate required fields
    if not email or not role:
        return jsonify({'message': 'Missing email or role'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    user = None
    user_id = None
    name = None

    if role == 'patient':
        # Patients don’t need password
        cursor.execute("SELECT patient_id, email, first_name, last_name FROM Patients WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            user_id = user['patient_id']
            name = f"{user['first_name']} {user['last_name']}"

    elif role == 'doctor':
        # Doctors don’t need password either
        cursor.execute("SELECT doctor_id, email, first_name, last_name, specialization FROM Doctors WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            user_id = user['doctor_id']
            name = f"Dr. {user['first_name']} {user['last_name']}"

    elif role == 'admin':
        # Admins require password
        if email == 'admin@hospital.com' and password == 'admin123':
            user = {'email': email}
            user_id = 'ADMIN001'
            name = 'Administrator'
        else:
            user = None

    cursor.close()
    conn.close()

    if user:
        token = jwt.encode({
            'user_id': user_id,
            'role': role,
            'name': name,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")

        return jsonify({
            'token': token,
            'user_id': user_id,
            'role': role,
            'name': name
        }), 200

    return jsonify({'message': 'Invalid credentials'}), 401

# ==================== PATIENT ENDPOINTS ====================

@app.route('/api/patient/profile', methods=['GET'])
@token_required
def get_patient_profile(current_user):
    if current_user['role'] != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT patient_id, first_name, last_name, gender, date_of_birth, 
               contact_number, address, registration_date, insurance_provider, 
               insurance_number, email
        FROM Patients WHERE patient_id = %s
    """, (current_user['user_id'],))
    
    patient = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if patient:
        patient['date_of_birth'] = str(patient['date_of_birth'])
        patient['registration_date'] = str(patient['registration_date'])
        return jsonify(patient), 200
    
    return jsonify({'message': 'Patient not found'}), 404

@app.route('/api/patient/appointments', methods=['GET'])
@token_required
def get_patient_appointments(current_user):
    if current_user['role'] != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT a.appointment_id, a.appointment_date, a.appointment_time, 
               a.reason_for_visit, a.status,
               d.first_name as doctor_first_name, d.last_name as doctor_last_name,
               d.specialization
        FROM Appointments a
        JOIN Doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (current_user['user_id'],))
    
    appointments = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for apt in appointments:
        apt['appointment_date'] = str(apt['appointment_date'])
        apt['appointment_time'] = str(apt['appointment_time'])
        apt['doctor_name'] = f"Dr. {apt['doctor_first_name']} {apt['doctor_last_name']}"
        del apt['doctor_first_name']
        del apt['doctor_last_name']
    
    return jsonify(appointments), 200

@app.route('/api/patient/treatments', methods=['GET'])
@token_required
def get_patient_treatments(current_user):
    if current_user['role'] != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT t.treatment_id, t.treatment_type, t.description, t.cost, 
               t.treatment_date, a.reason_for_visit
        FROM Treatments t
        JOIN Appointments a ON t.appointment_id = a.appointment_id
        WHERE a.patient_id = %s
        ORDER BY t.treatment_date DESC
    """, (current_user['user_id'],))
    
    treatments = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for t in treatments:
        t['treatment_date'] = str(t['treatment_date'])
        t['cost'] = float(t['cost'])
    
    return jsonify(treatments), 200

@app.route('/api/patient/billings', methods=['GET'])
@token_required
def get_patient_billings(current_user):
    if current_user['role'] != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT b.bill_id, b.bill_date, b.amount, b.payment_method, 
               b.payment_status, t.treatment_type
        FROM Billing b
        JOIN Treatments t ON b.treatment_id = t.treatment_id
        WHERE b.patient_id = %s
        ORDER BY b.bill_date DESC
    """, (current_user['user_id'],))
    
    billings = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for b in billings:
        b['bill_date'] = str(b['bill_date'])
        b['amount'] = float(b['amount'])
    
    return jsonify(billings), 200

@app.route('/api/doctors/available-by-slot', methods=['GET'])
@token_required
def get_available_doctors_by_slot(current_user):
    """Return list of doctors free at a given date and time"""
    date = request.args.get('date')
    time = request.args.get('time')

    if not date or not time:
        return jsonify({'message': 'Missing date or time'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT d.doctor_id, d.first_name, d.last_name, d.specialization
        FROM Doctors d
        WHERE d.doctor_id NOT IN (
            SELECT doctor_id FROM Appointments
            WHERE appointment_date = %s AND appointment_time = %s
            AND status IN ('Scheduled', 'Ongoing')
        )
        ORDER BY d.specialization, d.last_name
    """, (date, time))

    doctors = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(doctors), 200

@app.route('/api/patient/book-appointment', methods=['POST'])
@token_required
def book_appointment(current_user):
    if current_user['role'] != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Check if doctor is already booked for that date & time
    cursor.execute("""
        SELECT * FROM Appointments
        WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s
        AND status IN ('Scheduled', 'Ongoing')
    """, (data['doctor_id'], data['date'], data['time']))

    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'message': 'Doctor not available at this time'}), 409

    # Generate new appointment ID
    cursor.execute("SELECT appointment_id FROM Appointments ORDER BY appointment_id DESC LIMIT 1")
    last_id = cursor.fetchone()
    new_id = f"A{int(last_id[0][1:]) + 1:03d}" if last_id else "A001"

    cursor.execute("""
        INSERT INTO Appointments (appointment_id, patient_id, doctor_id,
                                  appointment_date, appointment_time,
                                  reason_for_visit, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled')
    """, (new_id, current_user['user_id'], data['doctor_id'],
          data['date'], data['time'], data['reason']))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Appointment booked successfully', 'appointment_id': new_id}), 201

# ==================== DOCTOR ENDPOINTS ====================

@app.route('/api/doctor/profile', methods=['GET'])
@token_required
def get_doctor_profile(current_user):
    if current_user['role'] != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT doctor_id, first_name, last_name, specialization, 
               phone_number, years_experience, hospital_branch, email
        FROM Doctors WHERE doctor_id = %s
    """, (current_user['user_id'],))
    
    doctor = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return jsonify(doctor), 200

@app.route('/api/doctor/appointments', methods=['GET'])
@token_required
def get_doctor_appointments(current_user):
    if current_user['role'] != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT a.appointment_id, a.appointment_date, a.appointment_time, 
               a.reason_for_visit, a.status,
               p.first_name as patient_first_name, p.last_name as patient_last_name,
               p.contact_number, p.patient_id
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.patient_id
        WHERE a.doctor_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (current_user['user_id'],))
    
    appointments = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for apt in appointments:
        apt['appointment_date'] = str(apt['appointment_date'])
        apt['appointment_time'] = str(apt['appointment_time'])
        apt['patient_name'] = f"{apt['patient_first_name']} {apt['patient_last_name']}"
        del apt['patient_first_name']
        del apt['patient_last_name']
    
    return jsonify(appointments), 200

@app.route('/api/doctor/update-appointment-status', methods=['PUT'])
@token_required
def update_appointment_status(current_user):
    if current_user['role'] != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403
    
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE Appointments 
        SET status = %s 
        WHERE appointment_id = %s AND doctor_id = %s
    """, (data['status'], data['appointment_id'], current_user['user_id']))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'message': 'Appointment status updated'}), 200

# ==================== DOCTOR ADDS TREATMENT ====================

@app.route('/api/doctor/add-treatment', methods=['POST'])
@token_required
def add_treatment(current_user):
    if current_user['role'] != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.json
    appointment_id = data.get('appointment_id')
    treatment_type = data.get('treatment_type')
    description = data.get('description')
    cost = data.get('cost')

    if not all([appointment_id, treatment_type, cost]):
        return jsonify({'message': 'Missing required fields'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ Check if appointment belongs to this doctor
    cursor.execute("SELECT * FROM Appointments WHERE appointment_id=%s AND doctor_id=%s",
                   (appointment_id, current_user['user_id']))
    appointment = cursor.fetchone()
    if not appointment:
        cursor.close()
        conn.close()
        return jsonify({'message': 'Invalid appointment'}), 404

    # ✅ Create treatment ID
    cursor.execute("SELECT treatment_id FROM Treatments ORDER BY treatment_id DESC LIMIT 1")
    last = cursor.fetchone()
    new_treatment_id = f"T{int(last['treatment_id'][1:]) + 1:03d}" if last else "T001"

    # ✅ Insert treatment record
    cursor.execute("""
        INSERT INTO Treatments (treatment_id, appointment_id, treatment_type, description, cost, treatment_date)
        VALUES (%s, %s, %s, %s, %s, CURDATE())
    """, (new_treatment_id, appointment_id, treatment_type, description, cost))
    conn.commit()

    # ✅ Auto-generate billing record
    cursor.execute("SELECT patient_id FROM Appointments WHERE appointment_id=%s", (appointment_id,))
    patient = cursor.fetchone()
    patient_id = patient['patient_id'] if patient else None

    cursor.execute("SELECT bill_id FROM Billing ORDER BY bill_id DESC LIMIT 1")
    last_bill = cursor.fetchone()
    new_bill_id = f"B{int(last_bill['bill_id'][1:]) + 1:03d}" if last_bill else "B001"

    cursor.execute("""
        INSERT INTO Billing (bill_id, patient_id, treatment_id, bill_date, amount, payment_method, payment_status)
        VALUES (%s, %s, %s, CURDATE(), %s, 'Pending', 'Pending')
    """, (new_bill_id, patient_id, new_treatment_id, cost))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        'message': 'Treatment and billing record added successfully',
        'treatment_id': new_treatment_id,
        'bill_id': new_bill_id
    }), 201

# ==================== ADMIN ENDPOINTS ====================

@app.route('/api/admin/all-patients', methods=['GET'])
@token_required
def get_all_patients(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM Patients ORDER BY registration_date DESC")
    patients = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for p in patients:
        p['date_of_birth'] = str(p['date_of_birth'])
        p['registration_date'] = str(p['registration_date'])
    
    return jsonify(patients), 200

@app.route('/api/admin/all-doctors', methods=['GET'])
@token_required
def get_all_doctors(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM Doctors")
    doctors = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify(doctors), 200

@app.route('/api/admin/all-appointments', methods=['GET'])
@token_required
def get_all_appointments(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT a.*, 
               p.first_name as patient_name, p.last_name as patient_last,
               d.first_name as doctor_name, d.last_name as doctor_last
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.patient_id
        JOIN Doctors d ON a.doctor_id = d.doctor_id
        ORDER BY a.appointment_date DESC
    """)
    appointments = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for apt in appointments:
        apt['appointment_date'] = str(apt['appointment_date'])
        apt['appointment_time'] = str(apt['appointment_time'])
    
    return jsonify(appointments), 200

@app.route('/api/admin/all-billings', methods=['GET'])
@token_required
def get_all_billings(current_user):
    if current_user['role'] != 'admin':
        return jsonify({'message': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT b.*, p.first_name, p.last_name
        FROM Billing b
        JOIN Patients p ON b.patient_id = p.patient_id
        ORDER BY b.bill_date DESC
    """)
    billings = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for b in billings:
        b['bill_date'] = str(b['bill_date'])
        b['amount'] = float(b['amount'])
    
    return jsonify(billings), 200

# ==================== COMMON ENDPOINTS ====================

@app.route('/api/doctors/available', methods=['GET'])
@token_required
def get_available_doctors(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT doctor_id, first_name, last_name, specialization, 
               hospital_branch, years_experience
        FROM Doctors
        ORDER BY specialization, last_name
    """)
    doctors = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify(doctors), 200

from flask import render_template

# ========== FRONTEND ROUTES ==========
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/admin-dashboard')
def admin_dashboard():
    return render_template('admin-dashboard.html')

@app.route('/doctor-dashboard')
def doctor_dashboard():
    return render_template('doctor-dashboard.html')

@app.route('/patient-dashboard')
def patient_dashboard():
    return render_template('patient-dashboard.html')

@app.route('/logout')
def logout():
    return render_template('login.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)