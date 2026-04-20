import os
import uuid
import boto3
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv("SECRET_KEY", "aws_cloud_secret_123")

# AWS Configurations
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client('s3', region_name=AWS_REGION)
sqs_client = boto3.client('sqs', region_name=AWS_REGION)

# Database Setup (SQLite for users/metadata)
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, password TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS images 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, 
                       filename TEXT, original_url TEXT, thumbnail_url TEXT, 
                       status TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        conn.close()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        user = cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        conn.close()
        if user:
            session['username'] = username
            return redirect(url_for('dashboard'))
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'username' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        file = request.files['image']
        if file:
            filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            
            # 1. Upload Original to S3
            try:
                s3_client.upload_fileobj(file, S3_BUCKET, f"uploads/{filename}")
                
                # 2. Save Metadata to DB
                original_url = f"https://{S3_BUCKET}.s3.amazonaws.com/uploads/{filename}"
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("INSERT INTO images (username, filename, original_url, thumbnail_url, status, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                               (session['username'], filename, original_url, "", "Queued", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                conn.close()

                # 3. Send Message to SQS
                sqs_client.send_message(
                    QueueUrl=SQS_QUEUE_URL,
                    MessageBody=str({"filename": filename, "bucket": S3_BUCKET})
                )

                flash("Image uploaded and queued for processing!", "success")
                return redirect(url_for('gallery'))
            except Exception as e:
                flash(f"Error: {str(e)}", "danger")
                
    return render_template('upload.html')

@app.route('/gallery')
def gallery():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    images = cursor.execute("SELECT * FROM images WHERE username=? ORDER BY id DESC", (session['username'],)).fetchall()
    conn.close()
    return render_template('gallery.html', images=images)

@app.route('/status')
def status():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # In real AWS, DynamoDB would update this. Here we simulate status refresh.
    logs = cursor.execute("SELECT filename, status, timestamp FROM images WHERE username=? ORDER BY id DESC", (session['username'],)).fetchall()
    conn.close()
    return render_template('status.html', logs=logs)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)