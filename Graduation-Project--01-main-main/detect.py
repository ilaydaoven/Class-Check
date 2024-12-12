import cv2
import numpy as np
from datetime import datetime
import mysql.connector
import face_recognition
import os
import pickle
from PIL import ImageFont, ImageDraw, Image
import tkinter as tk
import threading
import uuid
import dlib
from scipy.spatial import distance

# Göz kırpma tespiti için sabitler
EYE_AR_THRESH = 0.2
EYE_AR_CONSEC_FRAMES = 3

# Göz kırpma tespiti için sayaç
COUNTER = 0
BLINK_DETECTED = False

hangisinif = "T404"

# MySQL bağlantısı kurulumu
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="classcheck"
)
cursor = db.cursor()

# Sabitler ve değişkenlerin tanımlanması
confidence_threshold = 0.6  # Gerektiği şekilde ayarlayın
detected_ids = set()
popup_shown_for_ids = set()  # Pop-up gösterilmiş yüzlerin ID'lerini izlemek için
predefined_classname = "T404"

# Yüz kodlamalarını veritabanından yükle
known_face_encodings = []
known_face_ids = []

cursor.execute("SELECT student_id, face_encoding FROM students WHERE face_encoding IS NOT NULL")
for student_id, face_encoding_blob in cursor.fetchall():
    face_encoding = pickle.loads(face_encoding_blob)
    known_face_encodings.append(face_encoding)
    known_face_ids.append(student_id)

# ID'ye göre profili getirme fonksiyonu
def get_profile(studentid):
    cursor.execute("SELECT * FROM students WHERE student_id = %s", (studentid,))
    return cursor.fetchone()

# Bir öğrencinin zaten yoklama alınıp alınmadığını kontrol etme fonksiyonu
def is_already_marked(courseid, studentid, date):
    cursor.execute("SELECT * FROM attendance WHERE course_id = %s AND student_id = %s AND DATE(attendance_date) = %s",
                   (courseid, studentid, date))
    return cursor.fetchone() is not None

# Yoklama kaydı ekleme fonksiyonu
def add_attendance_record(courseid, studentid):
    cursor.execute("INSERT INTO attendance (attendance_id, course_id, student_id, attendance_date) VALUES (%s, %s, %s, NOW())",
                   (str(uuid.uuid4()), courseid, studentid))
    db.commit()

# Görüntüye metin bindirme fonksiyonu
def put_text(img, text, position, font_size=20, color=(0, 255, 127)):
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = ImageFont.truetype("arial.ttf", font_size)
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

# Pop-up mesajı gösterme fonksiyonu
def show_popup(name, mesaj):
    def popup():
        root = tk.Tk()
        root.title("Student recognized!")
        root.geometry("600x250")
        root.eval('tk::PlaceWindow . center')
        label = tk.Label(root, text=f"Hello {name} {mesaj} ", font=("Arial", 13))
        label.pack(expand=True)
        root.after(4000, root.destroy)

        root.mainloop()

    threading.Thread(target=popup).start()

# Göz kırpma tespiti için yardımcı fonksiyon
def eye_aspect_ratio(eye):
    A = distance.euclidean(eye[1], eye[5])
    B = distance.euclidean(eye[2], eye[4])
    C = distance.euclidean(eye[0], eye[3])
    ear = (A + B) / (2.0 * C)
    return ear

# Yüz tanıma işlemleri için global değişkenler
face_locations = []
face_encodings_current = []

# Dlib yüz ve göz tespiti için predictor yükle
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("resources/shape_predictor_68_face_landmarks.dat")

# Yüz tanıma fonksiyonu
def recognize_faces():
    global face_locations, face_encodings_current
    while True:
        ret, img = cam.read()
        if not ret:
            break

        rgb_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings_current = face_recognition.face_encodings(rgb_frame, face_locations)

# Kamerayı aç
cam = cv2.VideoCapture(0)
cam.set(3, 640)  # Genişlik ayarla
cam.set(4, 480)  # Yükseklik ayarla

# Arka plan resmini yükle
imgBackground = cv2.imread("resources/background.jpg")

# Yüz tanıma iş parçacığını başlat
recognition_thread = threading.Thread(target=recognize_faces)
recognition_thread.daemon = True
recognition_thread.start()

while True:
    ret, img = cam.read()
    if not ret:
        break

    img_with_faces = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rects = detector(gray, 0)

    for rect in rects:
        shape = predictor(gray, rect)
        shape = [(shape.part(i).x, shape.part(i).y) for i in range(68)]

        leftEye = shape[36:42]
        rightEye = shape[42:48]

        leftEAR = eye_aspect_ratio(leftEye)
        rightEAR = eye_aspect_ratio(rightEye)

        ear = (leftEAR + rightEAR) / 2.0

        # Eğer EAR değeri eşik değerinin altındaysa göz kırpma tespit edilir
        if ear < EYE_AR_THRESH:
            COUNTER += 1
        else:
            if COUNTER >= EYE_AR_CONSEC_FRAMES:
                BLINK_DETECTED = True
            COUNTER = 0

        if BLINK_DETECTED:
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings_current):
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding,
                                                         tolerance=1 - confidence_threshold)
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)

                if matches[best_match_index]:
                    studentid = known_face_ids[best_match_index]
                    profile = get_profile(studentid)

                    if profile is not None:
                        name = profile[1] + " " + profile[2]  # student_name ve student_surname
                        if studentid not in popup_shown_for_ids:  # Bu ID için pop-up zaten gösterilmiş mi kontrol et
                            current_day = datetime.now().weekday() + 1  # 1 (Pazartesi) - 7 (Pazar)
                            current_time = datetime.now().strftime("%H:%M:%S")
                            predefined_classname = "T404"

                            query = f"""
                                SELECT * FROM courses 
                                WHERE class_name = '{predefined_classname}' 
                                AND course_day = {current_day} 
                                AND attendance_start_time < '{current_time}' 
                                AND attendance_end_time > '{current_time}'
                            """

                            cursor.execute(query)
                            sonucders = cursor.fetchone()
                            db.commit()

                            try:
                                courseid = sonucders[0]
                            except:
                                show_popup(name, ', no lesson found at this time.')
                                popup_shown_for_ids.add(studentid)  # ID'yi sete ekle
                                continue

                            query = f"SELECT * FROM registeredStudents WHERE course_id= '{courseid}'"
                            cursor.execute(query)
                            dersekayitliogrenciler = cursor.fetchall()

                            dersekayitliogrencilerinidsi = []
                            suankizaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                            suankizamanGUN = datetime.now().strftime("%Y-%m-%d")

                            for item in dersekayitliogrenciler:
                                dersekayitliogrencilerinidsi.append(item[2])

                            if studentid in dersekayitliogrencilerinidsi:
                                dahaoncekayitlimisorgu = f"""
                                    SELECT * FROM attendance 
                                    WHERE course_id = '{courseid}' 
                                    AND student_id = '{studentid}' 
                                    AND attendance_date BETWEEN '{suankizamanGUN} 00:00:00' AND '{suankizamanGUN} 23:59:59'
                                """
                                cursor.execute(dahaoncekayitlimisorgu)
                                dahaoncekayitlimisorgucevap = cursor.fetchall()

                                if len(dahaoncekayitlimisorgucevap) > 0:
                                    show_popup(name, ', your attendance has already been taken.')
                                else:
                                    devamsizlikkaydetmesorgusu = "INSERT INTO attendance (attendance_id, course_id, student_id, attendance_date) VALUES (%s, %s, %s, %s);"
                                    cursor.execute(devamsizlikkaydetmesorgusu, (str(uuid.uuid4()), courseid, studentid, suankizaman))
                                    db.commit()
                                    show_popup(name, ', your attendace has been taken.')
                            else:
                                show_popup(name, ', you are not registered for this course.')

                            popup_shown_for_ids.add(studentid)  # Pop-up gösterildikten sonra ID'yi sete ekle

                        taninma_orani = (1 - face_distances[best_match_index]) * 100
                        img_with_faces = put_text(img_with_faces, f"Name: {name}", (left, bottom + 20))


            BLINK_DETECTED = False

    imgBackground[198:198 + 480, 147:147 + 640] = img_with_faces
    cv2.imshow("ClassCheck Attendance System", imgBackground)

    if cv2.waitKey(1) == ord("q"):
        break

cam.release()
cv2.destroyAllWindows()
