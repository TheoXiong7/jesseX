from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Configuration
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Custom Jinja2 filter for safe date formatting
@app.template_filter('safe_strftime')
def safe_strftime(date_value, format_string='%B %d, %Y'):
    """Safely format date values, handling both datetime objects and strings"""
    if not date_value:
        return 'Recently uploaded'
    
    try:
        if isinstance(date_value, str):
            # Try to parse string dates
            date_obj = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
        elif hasattr(date_value, 'strftime'):
            # Already a datetime object
            date_obj = date_value
        else:
            return 'Recently uploaded'
        
        return date_obj.strftime(format_string)
    except (ValueError, TypeError, AttributeError):
        return 'Recently uploaded'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Videos table
    c.execute('''CREATE TABLE IF NOT EXISTS videos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  description TEXT,
                  filename TEXT NOT NULL,
                  upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  featured BOOLEAN DEFAULT 0)''')
    
    # Admin users table (simple authentication)
    c.execute('''CREATE TABLE IF NOT EXISTS admin_users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL)''')
    
    # Create default admin user (password: admin123)
    admin_hash = generate_password_hash('admin123')
    c.execute('INSERT OR IGNORE INTO admin_users (username, password_hash) VALUES (?, ?)', 
              ('admin', admin_hash))
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def format_videos(videos):
    """Convert video rows to dictionaries with proper date formatting"""
    formatted_videos = []
    for video in videos:
        video_dict = dict(video)
        # Handle upload_date formatting
        if video_dict['upload_date']:
            try:
                # Try to parse the date string if it's stored as string
                if isinstance(video_dict['upload_date'], str):
                    date_obj = datetime.strptime(video_dict['upload_date'], '%Y-%m-%d %H:%M:%S')
                    video_dict['upload_date'] = date_obj
            except (ValueError, TypeError):
                video_dict['upload_date'] = None
        formatted_videos.append(video_dict)
    return formatted_videos

@app.route('/')
def home():
    conn = get_db_connection()
    featured_videos = conn.execute(
        'SELECT * FROM videos WHERE featured = 1 ORDER BY upload_date DESC LIMIT 3'
    ).fetchall()
    recent_videos = conn.execute(
        'SELECT * FROM videos ORDER BY upload_date DESC LIMIT 6'
    ).fetchall()
    conn.close()
    
    # Format videos for proper date handling
    featured_videos = format_videos(featured_videos)
    recent_videos = format_videos(recent_videos)
    
    return render_template('home.html', featured_videos=featured_videos, recent_videos=recent_videos)

@app.route('/highlights')
def highlights():
    conn = get_db_connection()
    # Get featured videos first
    featured_videos = conn.execute(
        'SELECT * FROM videos WHERE featured = 1 ORDER BY upload_date DESC'
    ).fetchall()
    # Get non-featured videos
    other_videos = conn.execute(
        'SELECT * FROM videos WHERE featured = 0 ORDER BY upload_date DESC'
    ).fetchall()
    conn.close()
    
    # Format videos for proper date handling
    featured_videos = format_videos(featured_videos)
    other_videos = format_videos(other_videos)
    
    return render_template('highlights.html', featured_videos=featured_videos, other_videos=other_videos)

@app.route('/social-work')
def social_work():
    return render_template('social_work.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM admin_users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            flash('Successfully logged in!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Successfully logged out!', 'success')
    return redirect(url_for('home'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    videos = conn.execute('SELECT * FROM videos ORDER BY upload_date DESC').fetchall()
    conn.close()
    
    # Format videos for proper date handling
    videos = format_videos(videos)
    
    return render_template('admin_dashboard.html', videos=videos)

@app.route('/admin/upload', methods=['POST'])
def upload_video():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    if 'video' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['video']
    title = request.form['title']
    description = request.form.get('description', '')
    featured = 'featured' in request.form
    
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to avoid conflicts
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        conn = get_db_connection()
        conn.execute('INSERT INTO videos (title, description, filename, featured) VALUES (?, ?, ?, ?)',
                    (title, description, filename, featured))
        conn.commit()
        conn.close()
        
        flash('Video uploaded successfully!', 'success')
    else:
        flash('Invalid file type! Please upload a video file.', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:video_id>')
def delete_video(video_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    video = conn.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if video:
        # Delete file from filesystem
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], video['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        conn.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
        flash('Video deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/toggle_featured/<int:video_id>')
def toggle_featured(video_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    video = conn.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if video:
        new_featured = not video['featured']
        conn.execute('UPDATE videos SET featured = ? WHERE id = ?', (new_featured, video_id))
        conn.commit()
        flash('Video featured status updated!', 'success')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)