from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import pytz
import openai
import json
from bson import ObjectId
import httpx
import boto3
from botocore.exceptions import ClientError
import io
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
import mylang4  # Import the LangChain module
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
#from question_prompt import QuestionPromptGenerator
from Utility.pdfmaker import CreatePDF
import logging
import re

# Ensure 'logging' directory exists
log_dir = "logging"
os.makedirs(log_dir, exist_ok=True)

# Create log filename with timestamp
log_filename = f"{log_dir}/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(message)s'
)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='dist', static_url_path='')

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Initialize MongoDB with configurable database and collections
try:
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    DB_NAME = os.getenv('DB_NAME', 'question_paper_db')
    REQUEST_COLLECTION = os.getenv('REQUEST_COLLECTION', 'question_requests')
    PAPER_COLLECTION = os.getenv('PAPER_COLLECTION', 'question_papers')
    
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    requests_collection = db[REQUEST_COLLECTION]
    papers_collection = db[PAPER_COLLECTION]
    logging.info("✅ MongoDB Connection Successful!")
except Exception as e:
    logging.info("❌ MongoDB Connection Error:", e)
    db = None

# Initialize OpenAI client
try:
    http_client = httpx.Client(
        base_url="https://api.openai.com/v1",
        timeout=60.0,
        follow_redirects=True
    )
    
    openai_client = openai.OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        http_client=http_client
    )
    logging.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logging.info(f"❌ Error initializing OpenAI client: {e}")
    raise

# Initialize AWS S3 client
try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )
    S3_BUCKET = os.getenv('S3_BUCKET_NAME')
    NOTES_BUCKET = os.getenv('NOTES_BUCKET_NAME')  # Separate bucket for notes
    logging.info("✅ AWS S3 Connection Successful!")
except Exception as e:
    logging.info("❌ AWS S3 Connection Error:", e)
    s3_client = None


@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# Initialize the question generator
#question_generator = QuestionPromptGenerator()

@app.route('/api/generate-questions', methods=['POST'])
async def generate_questions():
    try:
        logging.info("Received request at /api/generate-questions")
        data = request.json
        logging.info("Request data:", data)

        # Validate required fields
        required_fields = ['subjectName', 'classGrade', 'topics']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f"Missing required field: {field}"
                }), 400

        # Save request to MongoDB
        data['created_at'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
        request_id = requests_collection.insert_one(data).inserted_id

        # --- Load vectorstore if it exists ---
        vectorstore = None
        vectorstore_path = "vectorstores/latest"
        if os.path.exists(vectorstore_path):
            try:
                from langchain_community.vectorstores import FAISS
                from langchain_openai import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings()
                vectorstore = FAISS.load_local(vectorstore_path, embeddings, allow_dangerous_deserialization=True)
                logging.info("Loaded vectorstore from", vectorstore_path)
            except Exception as e:
                logging.info(f"Could not load vectorstore: {e}")
                vectorstore = None

        # Generate questions for all topics
        all_questions = []
        for topic in data['topics']:
            topic_data = {
                **topic,
                'subjectName': data.get('subjectName', ''),
                'classGrade': data.get('classGrade', '')
            }
            # Ensure numQuestions is int
            if 'numQuestions' in topic_data:
                try:
                    topic_data['numQuestions'] = int(topic_data['numQuestions'])
                except Exception:
                    topic_data['numQuestions'] = 1

            # Use vectorstore if available, else fallback to general
            questions = mylang4.question_generator.generate_questions(topic_data, vectorstore)
            all_questions.append({
                'topic': topic_data.get('sectionName', ''),
                'questions': questions['questions'],
                'cached': False
            })
        #catching means bringing questions from past based on smae settings.

        # Save generated questions to MongoDB
        paper_data = {
            'request_id': str(request_id),
            'questions': all_questions,
            'created_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
            'previous_paper_id': data.get('previous_paper_id')
        }
        paper_id = papers_collection.insert_one(paper_data).inserted_id

        # Generate PDF and upload to S3
        pdf_filename = f"question_paper_{paper_id}.pdf"
        pdf_buffer = CreatePDF.generate(all_questions, pdf_filename, class_grade=data.get('classGrade', ''), subject_name=data.get('subjectName', ''))

        # Upload to S3
        try:
            s3_client.upload_fileobj(
                pdf_buffer,
                S3_BUCKET,
                pdf_filename,
                ExtraArgs={'ContentType': 'application/pdf'}
            )
            logging.info(f"PDF uploaded to S3: {pdf_filename}")
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': pdf_filename
                },
                ExpiresIn=3600
            )

        except Exception as e:
            logging.info(f"Error with S3: {e}")
            url = None

        
        # After PDF generation and S3 upload
        local_pdf_path = 'temp_uploads/latest.pdf'
        if os.path.exists(local_pdf_path):
            try:
                os.remove(local_pdf_path)
                logging.info(f"Cleaned up temporary PDF file: {local_pdf_path}")
            except Exception as e:
                logging.warning(f"Failed to delete temporary PDF: {e}")

        # Clean up vectorstore directory if it exists 
        if os.path.exists(vectorstore_path):
            try:
                import shutil
                shutil.rmtree(vectorstore_path)
                logging.info(f"Cleaned up vectorstore directory: {vectorstore_path}")
            except Exception as e:
                logging.warning(f"Failed to delete vectorstore directory: {e}")
        
        return jsonify({
            'success': True,
            'paper_id': str(paper_id),
            'questions': all_questions,
            'pdf_url': url
        })

    except Exception as e:
        logging.info("Error in /api/generate-questions:", str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/download-pdf/<paper_id>', methods=['GET'])
def download_pdf(paper_id):
    try:
        filename = f"question_paper_{paper_id}.pdf"
        # Generate a pre-signed URL for the S3 object
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': filename
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        return jsonify({
            'success': True,
            'url': url
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/upload-note', methods=['POST'])
def upload_note():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400

        # Generate unique filename
        filename = f"notes/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

        temp_folder = 'temp_uploads'
        os.makedirs(temp_folder, exist_ok=True)
        local_path = os.path.join(temp_folder, 'latest.pdf')
        file.save(local_path)

        # Upload to S3 (no metadata)
        s3_client.upload_fileobj(
            file,
            NOTES_BUCKET,
            filename,
            ExtraArgs={'ContentType': 'application/pdf'}
        )

        # Save note metadata to MongoDB
        note_data = {
            'filename': filename,
            'original_name': file.filename,
            'uploaded_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
            's3_url': f"s3://{NOTES_BUCKET}/{filename}"
        }
        notes_collection = db['notes']
        note_id = notes_collection.insert_one(note_data).inserted_id

        return jsonify({
            'success': True,
            'note_id': str(note_id),
            'filename': file.filename
        })

    except Exception as e:
        logging.info(f"Error uploading note: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analyse-note', methods=['POST'])
def analyse_note():
    try:
        local_pdf_path = 'temp_uploads/latest.pdf'
        if not os.path.exists(local_pdf_path):
            return jsonify({'success': False, 'error': 'No PDF found to analyze'}), 400

        vectorstore_path = f'vectorstores/latest'
        os.makedirs(vectorstore_path, exist_ok=True)
        vectorstore, chunks = mylang4.document_processor.process_uploaded_document(local_pdf_path, persist_directory=vectorstore_path)

        

        return jsonify({'success': True})
    except Exception as e:
        logging.info(f"Error in analyse_note: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logging.info(f"🚀 Server starting on http://localhost:{port}")
    logging.info(f"📁 Serving static files from: {os.path.abspath(app.static_folder)}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )