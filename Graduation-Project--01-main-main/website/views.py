from flask import Blueprint, render_template, request, jsonify, session
from .auth import get_db_connection
import face_recognition
import pickle
import os
from flask import Blueprint, render_template, request, jsonify
import mysql.connector
import face_recognition
import pickle
import os
from werkzeug.utils import secure_filename
views = Blueprint('views', __name__)

@views.route('/')
def index():
    return render_template('base.html')

@views.route('/login')
def login():
    return render_template('login.html')

@views.route('/signup')
def signup():
    return render_template('signup.html')

@views.route('/authorized_login')
def authorized_login():
    return render_template('authorized_login.html')



@views.route('/toggle_attendance/<student_id>', methods=['POST'])
def toggle_attendance(student_id):
    data = request.get_json()
    attendance_date = data.get('attendance_date')
    course_id = data.get('course_id')
    
    if not attendance_date or not course_id:
        return jsonify({"success": False, "error": "Attendance date or course ID not provided"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if the student is already marked as present for the given date and course
    cursor.execute("""
        SELECT attendance_id 
        FROM attendance 
        WHERE student_id = %s 
        AND course_id = %s
        AND DATE(attendance_date) = %s
    """, (student_id, course_id, attendance_date))
    attendance_record = cursor.fetchone()

    if attendance_record:
        # If present, remove the attendance record using the attendance_id
        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_record['attendance_id'],))
    else:
        # If absent, add an attendance record
        cursor.execute("""
            INSERT INTO attendance (attendance_id, course_id, student_id, attendance_date) 
            VALUES (UUID(), %s, %s, %s)
        """, (course_id, student_id, attendance_date))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True})

@views.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    teacher_id = session.get('teacher_id')
    cursor.execute("SELECT course_id, course_name FROM courses WHERE teacher_id = %s", (teacher_id,))
    courses = cursor.fetchall()
    cursor.close()
    conn.close()

    selected_date = None
    selected_course_id = None
    students = []

    if request.method == 'POST':
        selected_course_id = request.form.get('class_name')
        selected_date = request.form.get('attendance_date')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.student_id, s.student_name, s.student_surname, 
                   CASE WHEN a.student_id IS NOT NULL THEN 1 ELSE 0 END AS present
            FROM students s
            LEFT JOIN registeredstudents rs ON s.student_id = rs.student_id
            LEFT JOIN attendance a ON s.student_id = a.student_id AND DATE(a.attendance_date) = %s
            WHERE rs.course_id = %s
        """
        cursor.execute(query, (selected_date, selected_course_id))
        students = cursor.fetchall()
        cursor.close()
        conn.close()

    return render_template('teacher_login.html', courses=courses, students=students, selected_date=selected_date, selected_course_id=selected_course_id)

@views.route('/filter_attendances', methods=['POST'])
def filter_attendances():
    selected_course_id = request.form.get('class_name')
    selected_date = request.form.get('attendance_date')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT s.student_id, s.student_name, s.student_surname, 
               CASE WHEN a.student_id IS NOT NULL THEN 1 ELSE 0 END AS present,
               rs.course_id
        FROM students s
        LEFT JOIN registeredstudents rs ON s.student_id = rs.student_id
        LEFT JOIN attendance a ON s.student_id = a.student_id AND DATE(a.attendance_date) = %s AND a.course_id = %s
        WHERE rs.course_id = %s
    """
    cursor.execute(query, (selected_date, selected_course_id, selected_course_id))
    students = cursor.fetchall()
    cursor.close()
    conn.close()

    teacher_id = session.get('teacher_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT course_id, course_name FROM courses WHERE teacher_id = %s", (teacher_id,))
    courses = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('teacher_login.html', courses=courses, students=students, selected_date=selected_date, selected_course_id=selected_course_id)
@views.route('/add_teacher')
def add_teacher():
    return render_template('add_teacher.html')

@views.route('/add_course')
def add_course():
    return render_template('add_course.html')

@views.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        student_id = request.form['student_id']
        student_name = request.form['student_name']
        student_surname = request.form['student_surname']
        images = request.files.getlist('images')

        # Ensure the user uploads exactly 5 images
        if len(images) != 5:
            return jsonify({"success": False, "message": "Please upload exactly 5 images."})

        # Save images to a temporary directory
        image_dir = os.path.join("static", "uploads", student_id)
        os.makedirs(image_dir, exist_ok=True)

        image_paths = []
        for image in images:
            filename = secure_filename(image.filename)
            image_path = os.path.join(image_dir, filename)
            image.save(image_path)
            image_paths.append(image_path)

        # Train the model and get face encodings
        face_encodings = []
        for image_path in image_paths:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                face_encodings.append(encodings[0])

        if not face_encodings:
            return jsonify({"success": False, "message": "No faces found in the uploaded images."})

        # Compute the average face encoding
        avg_encoding = list(map(lambda x: sum(x)/len(x), zip(*face_encodings)))

        # Store the student's information and face encoding in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO students (student_id, student_name, student_surname, face_encoding) VALUES (%s, %s, %s, %s)",
                       (student_id, student_name, student_surname, pickle.dumps(avg_encoding)))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": "Student added successfully."})

    return render_template('add_student.html')

@views.route('/attendances')
def attendances():
    return render_template('authorize_attendances.html')

@views.route('/teacherstudentclass')
def teacherstudentclass_list():
    return render_template('teacherstudentclass.html')

@views.route('/fetch_teachers')
def fetch_teachers():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT teacher_id, teacher_name, teacher_surname FROM teachers")
    teachers = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'teachers': teachers})

@views.route('/fetch_courses_by_teacher', methods=['POST'])
def fetch_courses_by_teacher():
    teacher_id = request.json.get('teacher_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT course_id, course_name FROM courses WHERE teacher_id = %s", (teacher_id,))
    courses = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'courses': courses})

@views.route('/fetch_students_by_course', methods=['POST'])
def fetch_students_by_course():
    course_id = request.json.get('course_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.student_id, s.student_name, s.student_surname
        FROM students s
        JOIN registeredstudents rs ON s.student_id = rs.student_id
        WHERE rs.course_id = %s
    """, (course_id,))
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'students': students})

@views.route('/filter_attendancesADMIN', methods=['POST'])
def filter_attendancesADMIN():
    course_id = request.form.get('course_id')
    attendance_date = request.form.get('attendance_date')

    conditions = []
    params = []

    if course_id:
        conditions.append("a.course_id = %s")
        params.append(course_id)
    if attendance_date:
        conditions.append("DATE(a.attendance_date) = %s")
        params.append(attendance_date)

    if not conditions:
        return jsonify([])  # Hiçbir koşul verilmezse boş sonuç döndür

    query = f"""
        SELECT a.course_id, a.student_id, a.attendance_date
        FROM attendance a
        WHERE {' AND '.join(conditions)}
    """

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params)
    attendances = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(attendances)

@views.route('/enroll_student')
def enroll_student():
    return render_template('enroll_student.html')

