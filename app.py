from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
import os, zipfile, tempfile, shutil, fitz
import docx2txt, spacy, csv

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'zip'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

nlp = spacy.load('en_core_web_sm')
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(path):
    try:
        doc = fitz.open(path)
        return " ".join([page.get_text() for page in doc])
    except:
        return ""

def extract_text_from_docx(path):
    return docx2txt.process(path)

def extract_skills_from_text(text, skill_list):
    doc = nlp(text.lower())
    return list(set([token.text for token in doc if token.text in skill_list]))

def parse_resume(file_path, skill_list):
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        text = extract_text_from_pdf(file_path)
    elif ext == 'docx':
        text = extract_text_from_docx(file_path)
    else:
        return {}
    matched_skills = extract_skills_from_text(text, skill_list)
    if not matched_skills:
        return {}
    match_score = int((len(matched_skills) / len(skill_list)) * 100) if skill_list else 0
    return {
        "file": os.path.basename(file_path),
        "skills": matched_skills,
        "score": match_score
    }

def process_files(uploaded_files, skill_list):
    results = []
    for file in uploaded_files:
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            if filename.endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    temp_dir = tempfile.mkdtemp()
                    zip_ref.extractall(temp_dir)
                    for root, _, files in os.walk(temp_dir):
                        for f in files:
                            if allowed_file(f):
                                res = parse_resume(os.path.join(root, f), skill_list)
                                if res: results.append(res)
                    shutil.rmtree(temp_dir)
            else:
                res = parse_resume(file_path, skill_list)
                if res: results.append(res)
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scan', methods=['POST'])
def scan():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files part'}), 400

    custom_skills = request.form.get('custom_skills', '')
    selected_skills = request.form.get('selected_skills', '')
    combined = (custom_skills + ',' + selected_skills).lower()
    skill_list = list(set([s.strip() for s in combined.split(',') if s.strip()]))

    files = request.files.getlist('files[]')
    results = process_files(files, skill_list)
    results.sort(key=lambda x: x['score'], reverse=True)

    csv_path = os.path.join(app.config['UPLOAD_FOLDER'], 'results.csv')
    with open(csv_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['file', 'skills', 'score'])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "file": r['file'],
                "skills": ", ".join(r['skills']),
                "score": r['score']
            })

    return jsonify(results=results)

@app.route('/download')
def download():
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], 'results.csv'), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)