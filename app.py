from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import jwt
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import os

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'e3c81b58bdd9a2d64fd511b3ed8a0868394c7d351e02c70fba9bdc4796a18701'

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '#Ananya19',  
    'database': 'hospital_management'
}

def generate_entity_id(cursor, table, column, prefix):
    cursor.execute(f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1")
    last = cursor.fetchone()
    if not last or not last.get(column):
        return f"{prefix}001"
    raw = str(last[column])
    try:
        numeric = int(raw[len(prefix):])
    except (ValueError, TypeError):
        numeric = 0
    return f"{prefix}{numeric + 1:03d}"

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error: {e}")
        return None

# Helper: convert mysql.connector.Error to JSON-friendly dict
def db_error_to_response(e):
    try:
        err_msg = str(e)
    except:
        err_msg = "Database error"
    return {'message': 'Database error', 'error': err_msg}

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

@app.route('/api/login/request-otp', methods=['POST'])
def request_login_otp():
    """
    OTP/email-based login has been disabled for patients and doctors.
    Admin login remains email + password via /api/login.
    """
    return jsonify({'message': 'OTP/email login disabled for patients and doctors. Use identifier (ID) login.'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    print("Login request received:", request.json)
    data = request.json or {}
    role = data.get('role')
    email = data.get('email')
    password = data.get('password', '')
    identifier = data.get('identifier')

    if not role:
        return jsonify({'message': 'Missing role'}), 400

    # Admin: unchanged (email + password)
    if role == 'admin':
        if email == 'admin@hospital.com' and password == 'admin123':
            token = jwt.encode({
                'user_id': 'ADMIN001',
                'role': role,
                'name': 'Administrator',
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm="HS256")

            return jsonify({
                'token': token,
                'user_id': 'ADMIN001',
                'role': role,
                'name': 'Administrator'
            }), 200
        return jsonify({'message': 'Invalid credentials'}), 401

    # Only allow patient or doctor below
    if role not in ('patient', 'doctor'):
        return jsonify({'message': 'Invalid role'}), 400

    # Enforce identifier-only login for patient/doctor
    if not identifier or not isinstance(identifier, str) or not identifier.strip():
        return jsonify({'message': 'Identifier (ID) is required for patient/doctor login'}), 400

    normalized_identifier = identifier.strip()

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    table = 'Patients' if role == 'patient' else 'Doctors'
    id_column = 'patient_id' if role == 'patient' else 'doctor_id'
    user = None

    try:
        cursor.execute(
            f"SELECT {id_column}, first_name, last_name FROM {table} WHERE {id_column} = %s",
            (normalized_identifier,)
        )
        user = cursor.fetchone()
    except Error as e:
        return jsonify(db_error_to_response(e)), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

    if not user:
        return jsonify({'message': 'Invalid identifier'}), 401

    user_id = user[id_column]
    if role == 'patient':
        name = f"{user['first_name']} {user['last_name']}"
    else:
        name = f"Dr. {user['first_name']} {user['last_name']}"

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
    # small safety: if DB connection failed
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
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

# ==================== PATIENT: book_appointment ====================

@app.route('/api/patient/book-appointment', methods=['POST'])
@token_required
def book_appointment(current_user):
    if current_user.get('role') != 'patient':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor()

    try:
        # basic required fields
        doctor_id = data.get('doctor_id')
        date = data.get('date')
        time = data.get('time')
        reason_raw = (data.get('reason') or '').strip()
        other_reason = (data.get('other_reason') or '').strip()

        # If the frontend sent 'Other' selection but included text in other_reason,
        # prefer the custom text. The frontend also sends final reason in `reason`,
        # but this logic ensures we accept either.
        final_reason = reason_raw
        if reason_raw.lower() in ('other', '') and other_reason:
            final_reason = other_reason

        if not doctor_id or not date or not time or not final_reason:
            return jsonify({'message': 'Missing required fields'}), 400

        # ✅ Check if doctor is already booked for that date & time
        cursor.execute("""
            SELECT COUNT(*) FROM Appointments
            WHERE doctor_id = %s AND appointment_date = %s AND appointment_time = %s
              AND status IN ('Scheduled','Ongoing')
        """, (doctor_id, date, time))
        clash_count = cursor.fetchone()[0]
        if clash_count and clash_count > 0:
            return jsonify({'message': 'Doctor already has an appointment at that time.'}), 400

        # Generate new appointment_id similar to existing logic (preserve your style)
        cursor.execute("SELECT appointment_id FROM Appointments ORDER BY appointment_id DESC LIMIT 1")
        last_id = cursor.fetchone()
        last_val = last_id[0] if last_id else None
        try:
            new_id = f"A{int(last_val[1:]) + 1:03d}" if last_val else "A001"
        except Exception:
            # fallback if the existing appointment_id format is unexpected
            new_id = last_val and f"A{int(re.sub('[^0-9]', '', last_val)) + 1:03d}" or "A001"

        # Insert appointment using final_reason
        cursor.execute("""
            INSERT INTO Appointments (appointment_id, patient_id, doctor_id,
                                      appointment_date, appointment_time,
                                      reason_for_visit, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled')
        """, (new_id, current_user['user_id'], doctor_id, date, time, final_reason))

        conn.commit()

        return jsonify({'message': 'Appointment booked', 'appointment_id': new_id}), 200

    except Error as e:
        try:
            conn.rollback()
        except:
            pass
        return jsonify(db_error_to_response(e)), 400

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return jsonify({'message': 'Unexpected error', 'error': str(e)}), 500

    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

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

@app.route('/api/doctors/available', methods=['GET'])
@token_required
def get_available_doctors(current_user):
    # Optional: allow access to all authenticated users (or only admins) --
    # current_user is the decoded JWT from token_required.
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT doctor_id, first_name, last_name, specialization, 
                   hospital_branch, years_experience
            FROM Doctors
            ORDER BY specialization, last_name
        """)
        doctors = cursor.fetchall()
    except Error as e:
        cursor.close()
        conn.close()
        return jsonify(db_error_to_response(e)), 400

    cursor.close()
    conn.close()
    return jsonify(doctors), 200

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

@app.route('/api/doctor/add-treatment', methods=['POST'])
@token_required
def doctor_add_treatment(current_user):
    if current_user.get('role') != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    appointment_id = (data.get('appointment_id') or '').strip()
    treatment_type = (data.get('treatment_type') or '').strip()
    description = (data.get('description') or '').strip()
    cost = data.get('cost')

    if not appointment_id or not treatment_type or not cost:
        return jsonify({'message': 'Missing required fields'}), 400

    try:
        cost_val = float(cost)
    except:
        return jsonify({'message': 'Invalid cost value'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        # validate appointment belongs to doctor
        cursor.execute("SELECT appointment_id, doctor_id, patient_id FROM Appointments WHERE appointment_id=%s",
                       (appointment_id,))
        apt = cursor.fetchone()
        if not apt:
            return jsonify({'message': 'Appointment not found'}), 404

        if str(apt['doctor_id']) != str(current_user['user_id']):
            return jsonify({'message': 'You are not authorized for this appointment'}), 403

        patient_id = apt['patient_id']

        # generate treatment id
        treatment_id = generate_entity_id(cursor, "Treatments", "treatment_id", "T")
        today = datetime.utcnow().strftime('%Y-%m-%d')

        # insert treatment
        cursor.execute("""
            INSERT INTO Treatments (treatment_id, appointment_id, treatment_type, description, cost, treatment_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (treatment_id, appointment_id, treatment_type, description, cost_val, today))

        # generate bill id
        bill_id = generate_entity_id(cursor, "Billing", "bill_id", "B")

        # insert billing (MATCHES YOUR TABLE)
        cursor.execute("""
            INSERT INTO Billing (bill_id, patient_id, treatment_id, bill_date, amount, payment_method, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (bill_id, patient_id, treatment_id, today, cost_val, "Not Paid", "Pending"))

        conn.commit()

        return jsonify({
            "message": "Treatment & Billing created",
            "treatment_id": treatment_id,
            "bill_id": bill_id
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify(db_error_to_response(e)), 400

    finally:
        cursor.close()
        conn.close()

@app.route('/api/doctor/billings', methods=['GET'])
@token_required
def get_doctor_billings(current_user):
    # only doctors allowed
    if current_user.get('role') != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        # Join Billing -> Treatments -> Appointments -> Patients
        # This returns appointment_id (from Appointments) even though Billing doesn't store appointment_id directly.
        cursor.execute("""
            SELECT
                b.bill_id,
                a.appointment_id,
                p.patient_id,
                p.first_name,
                p.last_name,
                t.treatment_type,
                b.amount,
                b.bill_date,
                b.payment_method,
                b.payment_status
            FROM Billing b
            JOIN Treatments t ON b.treatment_id = t.treatment_id
            JOIN Appointments a ON t.appointment_id = a.appointment_id
            JOIN Patients p ON a.patient_id = p.patient_id
            WHERE a.doctor_id = %s
            ORDER BY b.bill_date DESC, b.bill_id DESC
        """, (current_user['user_id'],))

        bills = cursor.fetchall()
    except Error as e:
        cursor.close()
        conn.close()
        return jsonify(db_error_to_response(e)), 400
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

    # Normalize/shape response for frontend
    for b in bills:
        if b.get('bill_date') is not None:
            b['bill_date'] = str(b['bill_date'])
        try:
            b['amount'] = float(b['amount']) if b.get('amount') is not None else 0.0
        except:
            pass
        # add patient_name field expected by frontend
        first = b.pop('first_name', '') or ''
        last = b.pop('last_name', '') or ''
        b['patient_name'] = f"{first} {last}".strip()

    return jsonify(bills), 200

@app.route('/api/doctor/billings/<bill_id>/status', methods=['PUT'])
@token_required
def update_billing_status(current_user, bill_id):
    # Only doctors allowed
    if current_user.get('role') != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    new_status = data.get('payment_status')
    payment_method = (data.get('payment_method') or '').strip() or 'Cash'
    allowed_status = {'Completed', 'Paid', 'Pending', 'Cancelled', 'Not Paid'}
    if not new_status or new_status not in allowed_status:
        return jsonify({'message': 'Invalid billing status'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        # Verify the billing belongs to a treatment whose appointment is for this doctor
        cursor.execute("""
            SELECT b.bill_id, b.treatment_id, b.patient_id, b.amount, a.doctor_id
            FROM Billing b
            JOIN Treatments t ON b.treatment_id = t.treatment_id
            JOIN Appointments a ON t.appointment_id = a.appointment_id
            WHERE b.bill_id = %s
        """, (bill_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'message': 'Billing record not found'}), 404

        if str(row.get('doctor_id')) != str(current_user.get('user_id')):
            cursor.close()
            conn.close()
            return jsonify({'message': 'Unauthorized to modify this billing'}), 403

        # Perform update
        cursor.execute("""
            UPDATE Billing
            SET payment_status = %s, payment_method = %s
            WHERE bill_id = %s
        """, (new_status, payment_method, bill_id))

        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'message': 'Failed to update billing'}), 400

        conn.commit()

        # Return updated billing entry (joined for context)
        cursor.execute("""
            SELECT b.bill_id, b.bill_date, b.amount, b.payment_method, b.payment_status,
                   t.treatment_type, a.appointment_id, p.patient_id, p.first_name, p.last_name
            FROM Billing b
            JOIN Treatments t ON b.treatment_id = t.treatment_id
            JOIN Appointments a ON t.appointment_id = a.appointment_id
            JOIN Patients p ON a.patient_id = p.patient_id
            WHERE b.bill_id = %s
        """, (bill_id,))
        updated = cursor.fetchone()
    except Error as e:
        try:
            conn.rollback()
        except:
            pass
        cursor.close()
        conn.close()
        return jsonify({'message': 'Database error', 'error': str(e)}), 400
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        cursor.close()
        conn.close()
        return jsonify({'message': 'Unexpected error', 'error': str(e)}), 500

    cursor.close()
    conn.close()

    # shape response
    if updated:
        if updated.get('bill_date') is not None:
            updated['bill_date'] = str(updated['bill_date'])
        try:
            updated['amount'] = float(updated['amount']) if updated.get('amount') is not None else 0.0
        except:
            pass
        first = updated.pop('first_name', '') or ''
        last = updated.pop('last_name', '') or ''
        updated['patient_name'] = f"{first} {last}".strip()

    return jsonify({'message': 'Billing status updated', 'billing': updated}), 200

# --- /api/doctor/update-appointment-status handler ---

def db_error_to_response(exc: Exception) -> dict:
    """Simple helper to convert DB exceptions to a JSON-friendly dict.
    If your app already has a similar helper, you can remove this function.
    """
    try:
        msg = str(exc)
    except:
        msg = "Database error"
    return {"message": "Database error", "error": msg}


@app.route('/api/doctor/update-appointment-status', methods=['PUT'])
@token_required
def update_appointment_status(current_user):
    # Only doctors are allowed
    if current_user.get('role') != 'doctor':
        return jsonify({'message': 'Unauthorized'}), 403

    # Safely read JSON
    data = request.get_json(silent=True) or {}
    appointment_id = (data.get('appointment_id') or '').strip()
    incoming_status = (data.get('status') or '').strip()

    # Normalize & validate status
    normalized_status = incoming_status.capitalize()
    allowed_status = {'Scheduled', 'Completed', 'Cancelled', 'Ongoing'}

    if not appointment_id or normalized_status not in allowed_status:
        return jsonify({'message': 'Invalid appointment ID or status'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'DB connection failed'}), 500

    cursor = conn.cursor(dictionary=True)

    try:
        # 1) Check appointment belongs to this doctor
        cursor.execute("""
            SELECT appointment_id, patient_id, doctor_id, status,
                   appointment_date, appointment_time
            FROM Appointments
            WHERE appointment_id = %s AND doctor_id = %s
        """, (appointment_id, current_user['user_id']))
        appointment = cursor.fetchone()

        if not appointment:
            return jsonify({'message': 'Appointment not found'}), 404

        # Convert date/time so they’re JSON-safe
        if appointment.get('appointment_date') is not None:
            appointment['appointment_date'] = str(appointment['appointment_date'])
        if appointment.get('appointment_time') is not None:
            appointment['appointment_time'] = str(appointment['appointment_time'])

        # Already same status?
        if appointment['status'] == normalized_status:
            return jsonify({
                'message': f'Appointment already marked as {normalized_status.lower()}.',
                'appointment': appointment
            }), 200

        # 2) Update status
        cursor.execute("""
            UPDATE Appointments
            SET status = %s
            WHERE appointment_id = %s
        """, (normalized_status, appointment_id))

        conn.commit()

        # Update local copy to return
        appointment['status'] = normalized_status

        return jsonify({'message': 'Appointment status updated', 'appointment': appointment}), 200

    except Error as e:
        # This is where your "Database error" is coming from
        try:
            conn.rollback()
        except:
            pass
        print("MySQL error in update_appointment_status:", e)  # <-- watch this in terminal
        return jsonify(db_error_to_response(e)), 400

    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        print("Unexpected error in update_appointment_status:", e)
        return jsonify({'message': 'Unexpected error', 'error': str(e)}), 500

    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

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
    app.run(host='0.0.0.0', port=5000, debug=True)
