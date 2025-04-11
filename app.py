from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartcare.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'doctor' or 'patient'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    patients = db.relationship('Patient', backref='doctor', lazy=True)
    
    def __repr__(self):
        return f'<User {self.name}>'

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    condition = db.Column(db.String(200))
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    health_profile = db.relationship('HealthProfile', backref='patient', uselist=False, lazy=True)
    appointments = db.relationship('Appointment', backref='patient', lazy=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Patient {self.name}>'

class HealthProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), unique=True)
    height = db.Column(db.Float)  # in cm
    weight = db.Column(db.Float)  # in kg
    blood_type = db.Column(db.String(10))
    allergies = db.Column(db.String(200))
    medical_history = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def bmi(self):
        if self.height and self.weight:
            return round(self.weight / ((self.height/100) ** 2), 1)
        return None

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, canceled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    doctor = db.relationship('User', backref='doctor_appointments')

class HealthStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    heart_rate = db.Column(db.Integer)  # bpm
    temperature = db.Column(db.Float)   # Fahrenheit
    blood_pressure = db.Column(db.String(20))  # "120/80"
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables before first request
@app.before_first_request
def create_tables():
    db.create_all()

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            role=role
        )
        
        db.session.add(new_user)
        
        # If signing up as patient, create a basic patient record
        if role == 'patient':
            new_patient = Patient(
                name=name,
                age=0,  # Will be updated in profile
                gender='Other',
                condition='None',
                doctor_id=1  # Assign to default doctor or implement doctor selection
            )
            db.session.add(new_patient)
            new_user.patients.append(new_patient)
        
        db.session.commit()
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user_role = session['user_role']
    
    patients = []
    patient_data = None
    patient_stats = None
    appointments = []
    
    if user_role == 'doctor':
        patients = Patient.query.filter_by(doctor_id=user_id).all()
    else:
        # For patients, get their own record
        patient = Patient.query.filter_by(id=user_id).first()
        if patient:
            patient_data = patient.health_profile
            patient_stats = HealthStats.query.filter_by(patient_id=patient.id).order_by(HealthStats.recorded_at.desc()).first()
            appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.date, Appointment.time).all()
    
    return render_template('index.html', 
                         user_name=session['user_name'],
                         user_role=user_role,
                         patients=patients,
                         patient_data=patient_data,
                         patient_stats=patient_stats,
                         appointments=appointments)

@app.route('/update_health_profile', methods=['POST'])
def update_health_profile():
    if 'user_id' not in session or session['user_role'] != 'patient':
        flash('Please login as patient to update health profile', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Get the current patient (using user_id as patient_id)
        patient = Patient.query.filter_by(id=session['user_id']).first()
        
        if not patient:
            flash('Patient record not found', 'danger')
            return redirect(url_for('dashboard'))
        
        # Update basic patient info
        patient.age = int(request.form.get('age', 0))
        patient.gender = 'Other'  # You should add gender field to form
        
        # Update or create health profile
        health_profile = patient.health_profile
        if not health_profile:
            health_profile = HealthProfile(patient_id=patient.id)
            db.session.add(health_profile)
        
        # Update health profile fields
        health_profile.height = float(request.form.get('height', 0))
        health_profile.weight = float(request.form.get('weight', 0))
        health_profile.blood_type = request.form.get('blood_type', '')
        health_profile.allergies = request.form.get('allergies', '')
        health_profile.medical_history = request.form.get('medical_history', '')
        
        # Create a new health stats record
        new_stats = HealthStats(
            patient_id=patient.id,
            heart_rate=72,  # Default or could add form fields
            temperature=98.6,
            blood_pressure="120/80"
        )
        db.session.add(new_stats)
        
        db.session.commit()
        flash('Health profile updated successfully', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if 'user_id' not in session or session['user_role'] != 'doctor':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        gender = request.form['gender']
        condition = request.form['condition']
        
        new_patient = Patient(
            name=name,
            age=age,
            gender=gender,
            condition=condition,
            doctor_id=session['user_id']
        )
        
        db.session.add(new_patient)
        db.session.commit()
        
        flash('Patient added successfully', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)