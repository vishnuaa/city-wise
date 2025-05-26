from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session
import pandas as pd
import os
import pdfkit
from zipfile import ZipFile
from io import BytesIO
import threading
import time
import shutil
import logging

app = Flask(__name__)
app.secret_key = 'secretkey'  # needed for flash messages and session

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'Uploads')
PDF_FOLDER = os.path.join(BASE_DIR, 'city_pdfs')

def cleanup_folders():
    """Delete all files in UPLOAD_FOLDER and PDF_FOLDER after 5 seconds"""
    time.sleep(5)
    for folder in [UPLOAD_FOLDER, PDF_FOLDER]:
        try:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                            logger.debug(f"Deleted file: {file_path}")
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                            logger.debug(f"Deleted directory: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {e}")
                shutil.rmtree(folder)
                logger.debug(f"Deleted folder: {folder}")
        except Exception as e:
            logger.error(f"Error cleaning folder {folder}: {e}")

@app.route('/', methods=['GET'])
def index():
    """Render index page with no data unless explicitly loaded"""
    logger.debug(f"Index GET request, session: {session}")
    return render_template('index.html', city_groups=None, headers=None)

@app.route('/upload', methods=['POST'])
def upload():
    """Handle file upload and PDF generation"""
    logger.debug(f"Upload POST request, form data: {request.form}, files: {request.files}")
    file = request.files.get('excel')
    prefix = request.form.get('prefix', '').strip()

    if file and file.filename.endswith('.xlsx'):
        # Ensure folders exist
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(PDF_FOLDER, exist_ok=True)

        # Save file with unique name to avoid conflicts
        unique_filename = f"{int(time.time())}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(path)
        logger.debug(f"Saved Excel file: {path}")

        df = pd.read_excel(path)
        df = df.sort_values(by='CONTACTCITY')
        grouped = df.groupby('CONTACTCITY')

        city_groups = {}
        for city, group in grouped:
            city_groups[city] = group.to_dict(orient='records')

        headers = list(df.columns)

        # Generate PDFs with prefix
        options = {
            'page-size': 'A4',
            'orientation': 'Landscape',
            'encoding': "UTF-8",
        }

        for city, group in grouped:
            rows = group.to_dict(orient='records')
            html = render_template("city_pdf_template.html", city=city, headers=headers, rows=rows)
            filename = f"{prefix} {city}.pdf" if prefix else f"{city}.pdf"
            pdf_path = os.path.join(PDF_FOLDER, filename)
            pdfkit.from_string(html, pdf_path, options=options)
            logger.debug(f"Generated PDF: {pdf_path}")

        session['city_groups'] = city_groups
        session['headers'] = headers
        flash("PDFs generated successfully!")
        return redirect(url_for('display_data'))

    else:
        flash("Please upload a valid .xlsx file")
        return redirect(url_for('index'))

@app.route('/display', methods=['GET'])
def display_data():
    """Display uploaded data from session"""
    logger.debug(f"Display GET request, session: {session}")
    city_groups = session.get('city_groups', None)
    headers = session.get('headers', [])
    return render_template('index.html', city_groups=city_groups, headers=headers)

@app.route('/download_zip')
def download_zip():
    """Download ZIP and clear data"""
    logger.debug(f"Download ZIP request, session: {session}")
    if not os.path.exists(PDF_FOLDER) or not os.listdir(PDF_FOLDER):
        flash("No PDFs generated yet.")
        return redirect(url_for('index'))

    memory_file = BytesIO()
    with ZipFile(memory_file, 'w') as zf:
        for filename in os.listdir(PDF_FOLDER):
            if filename.endswith('.pdf'):
                file_path = os.path.join(PDF_FOLDER, filename)
                zf.write(file_path, arcname=filename)
                logger.debug(f"Added to ZIP: {filename}")

    memory_file.seek(0)

    # Clear session data
    session.clear()
    logger.debug("Session cleared")

    # Start cleanup in background thread
    threading.Thread(target=cleanup_folders, daemon=True).start()

    # Send file with cache-control headers
    response = send_file(memory_file, download_name='city_reports.zip', as_attachment=True)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/download/<city>')
def download_city_pdf(city):
    """Download individual city PDF"""
    logger.debug(f"Download city PDF: {city}, args: {request.args}")
    prefix = request.args.get('prefix', '')
    filename = f"{prefix} {city}.pdf" if prefix else f"{city}.pdf"
    filepath = os.path.join(PDF_FOLDER, filename)
    if not os.path.exists(filepath):
        flash("File not found")
        return redirect(url_for('index'))
    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)