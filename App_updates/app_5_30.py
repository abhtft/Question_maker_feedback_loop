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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import boto3
from botocore.exceptions import ClientError
import io
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
import mylang4  # Import the LangChain module
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
import tempfile
from question_prompt import QuestionPromptGenerator
from Utility.pdfmaker import CreatePDF
import logging
import re


# Ensure 'logging' directory exists
log_dir = "logging"
os.makedirs(log_dir, exist_ok=True)

# Create log filename with timestamp
log_filename = f"{log_dir}/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    FEEDBACK_COLLECTION = os.getenv('FEEDBACK_COLLECTION', 'paper_feedback')
    
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    requests_collection = db[REQUEST_COLLECTION]
    papers_collection = db[PAPER_COLLECTION]
    feedback_collection = db[FEEDBACK_COLLECTION]
    print("✅ MongoDB Connection Successful!")
except Exception as e:
    print("❌ MongoDB Connection Error:", e)
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
    print("✅ OpenAI client initialized successfully")
except Exception as e:
    print(f"❌ Error initializing OpenAI client: {e}")
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
    print("✅ AWS S3 Connection Successful!")
except Exception as e:
    print("❌ AWS S3 Connection Error:", e)
    s3_client = None

def get_feedback_context(paper_id):
    """Get relevant feedback for a paper to improve question generation"""
    try:
        feedback = list(feedback_collection.find(
            {'paper_id': paper_id},
            {'_id': 0, 'feedback': 1, 'suggestions': 1}
        ))
        if feedback:
            feedback_text = "\n".join([
                f"Feedback: {f['feedback']}\nSuggestions: {f['suggestions']}"
                for f in feedback
            ])
            return f"\nPrevious feedback to consider:\n{feedback_text}"
        return ""
    except Exception as e:
        print(f"Error getting feedback: {e}")
        return ""
    


def generate_question_prompt(topic_data, paper_id=None, note_id=None):
    """Enhanced prompt generation with note context"""
    feedback_context = get_feedback_context(paper_id) if paper_id else ""
    note_context = ""
    
    if note_id:
        try:
            note = db['notes'].find_one({'_id': ObjectId(note_id)})
            if note and note.get('text_content'):
                note_context = f"\nContext from uploaded notes:\n{note['text_content']}\n"
        except Exception as e:
            print(f"Error getting note context: {e}")
    
    return f"""You are an expert educator tasked to create questions.

Generate {topic_data.get('numQuestions', 1)} {topic_data.get('questionType', '')} questions for:

- Subject: {topic_data.get('subjectName', '')}
- Class/Grade: {topic_data.get('classGrade', '')}
- Topic: {topic_data.get('sectionName', '')}
- Difficulty Level: {topic_data.get('difficulty', '')}
- Bloom's Taxonomy Level: {topic_data.get('bloomLevel', '')}
- Intelligence Type: {topic_data.get('intelligenceType', '')}
- Intelligence SubType: {topic_data.get('intelligenceSubType', 'General')}

{note_context}

Additional Instructions: {topic_data.get('additionalInstructions', '')}

{feedback_context}

🔵 Strict Requirements:
1. Match exactly the specified difficulty and Bloom's level.
2. Test deep conceptual understanding, not rote memorization (unless instructed).
3. Use technical language appropriate for Class {topic_data.get('classGrade', '')} level.
4. Follow the {topic_data.get('questionType', '')} format precisely.
5. If MCQ:
    - Provide exactly 4 options.
    - Ensure all options are realistic, meaningful, and non-trivial (no obviously wrong answers).
6. For each question, provide:
    - Clear and concise question text
    - Correct answer
    - Step-by-step detailed explanation (why the correct answer is correct and why others are wrong, if relevant)
7. Avoid ambiguity or overlaps in options or question phrasing.
8. Do not repeat or slightly vary questions.
9. Incorporate feedback (if provided).
10. Use the provided note context to make questions more relevant and contextual.

🟢 Output Format (strictly JSON):
Example:
{{
  "questions": [
    {{
      "question": "What is the capital of France?",
      "options": ["Berlin", "London", "Paris", "Rome"],
      "answer": "Paris",
      "explanation": "Paris is the capital and most populous city of France."
    }}
  ]
}}
"""


@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

def generate_cache_key(topic_data):
    """Generate a cache key for the topic data"""
    key_data = {
        'subject': topic_data.get('subjectName', ''),
        'class': topic_data.get('classGrade', ''),
        'topic': topic_data.get('sectionName', ''),
        'type': topic_data.get('questionType', ''),
        'difficulty': topic_data.get('difficulty', ''),
        'bloom': topic_data.get('bloomLevel', ''),
        'intelligence': topic_data.get('intelligenceType', '')

    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

async def generate_questions_for_topic(topic_data, previous_paper_id=None):
    """Generate questions for a single topic with caching"""
    try:
        # Check cache first
        cache_key = generate_cache_key(topic_data)
        cached_questions = papers_collection.find_one(
            {
                'cache_key': cache_key,
                'created_at': {
                    '$gte': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
                }
            }
        )
        
        if cached_questions:
            print(f"Cache hit for topic: {topic_data['sectionName']}")
            return {
                'topic': topic_data['sectionName'],
                'questions': cached_questions['questions'],
                'cached': True
            }

        prompt = generate_question_prompt(topic_data, previous_paper_id)
        response = await asyncio.to_thread(
            lambda: openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert educational question generator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
        )
        
        questions = json.loads(response.choices[0].message.content)
        
        # Cache the results
        cache_data = {
            'cache_key': cache_key,
            'questions': questions['questions'],
            'created_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
        }
        papers_collection.insert_one(cache_data)
        
        return {
            'topic': topic_data['sectionName'],
            'questions': questions['questions'],
            'cached': False
        }
    except Exception as e:
        print(f"Error generating questions for topic {topic_data['sectionName']}: {str(e)}")
        raise

# Initialize the question generator
question_generator = QuestionPromptGenerator()

@app.route('/api/generate-questions', methods=['POST'])
async def generate_questions():
    try:
        print("Received request at /api/generate-questions")
        data = request.json
        print("Request data:", data)

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
                print("Loaded vectorstore from", vectorstore_path)
            except Exception as e:
                print(f"Could not load vectorstore: {e}")
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
            questions = question_generator.generate_questions(topic_data, vectorstore)
            all_questions.append({
                'topic': topic_data.get('sectionName', ''),
                'questions': questions['questions'],
                'cached': False
            })

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
            print(f"PDF uploaded to S3: {pdf_filename}")
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': pdf_filename
                },
                ExpiresIn=3600
            )
        except Exception as e:
            print(f"Error with S3: {e}")
            url = None

        return jsonify({
            'success': True,
            'paper_id': str(paper_id),
            'questions': all_questions,
            'pdf_url': url
        })

    except Exception as e:
        print("Error in /api/generate-questions:", str(e))
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

@app.route('/api/requests', methods=['GET'])
def get_requests():
    try:
        requests = list(requests_collection.find({}, {'_id': 1, 'created_at': 1, 'subjectName': 1, 'classGrade': 1}))
        for req in requests:
            req['_id'] = str(req['_id'])
        return jsonify(requests)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/papers', methods=['GET'])
def get_papers():
    try:
        papers = list(papers_collection.find({}, {'_id': 1, 'created_at': 1, 'request_id': 1}))
        for paper in papers:
            paper['_id'] = str(paper['_id'])
        return jsonify(papers)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/submit-feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        paper_id = data.get('paper_id')
        feedback = data.get('feedback')
        suggestions = data.get('suggestions')
        
        if not all([paper_id, feedback]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
            
        feedback_data = {
            'paper_id': paper_id,
            'feedback': feedback,
            'suggestions': suggestions,
            'created_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        feedback_id = feedback_collection.insert_one(feedback_data).inserted_id
        return jsonify({
            'success': True,
            'feedback_id': str(feedback_id)
        })
        
    except Exception as e:
        print("Error in /api/submit-feedback:", str(e))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/get-feedback/<paper_id>', methods=['GET'])
def get_feedback(paper_id):
    try:
        feedback = list(feedback_collection.find(
            {'paper_id': paper_id},
            {'_id': 0, 'feedback': 1, 'suggestions': 1, 'created_at': 1}
        ))
        return jsonify({
            'success': True,
            'feedback': feedback
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
        print(f"Error uploading note: {e}")
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

        # Update note record with vectorstore path
        #db['notes'].update_one({'_id': ObjectId(note_id)}, {'$set': {'vectorstore_path': vectorstore_path}})

        # Clean up local PDF
        if os.path.exists(local_pdf_path):
            os.remove(local_pdf_path)

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in analyse_note: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

def extract_text_from_pdf(pdf_file):
    """Extract text content from PDF file"""
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Server starting on http://localhost:{port}")
    print(f"📁 Serving static files from: {os.path.abspath(app.static_folder)}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )