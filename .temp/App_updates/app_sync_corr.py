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
from asgiref.sync import async_to_sync

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
    NOTES_BUCKET = os.getenv('NOTES_BUCKET_NAME','notes-bucket')  # Separate bucket for notes
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

Generate {topic_data['numQuestions']} {topic_data['questionType']} questions for:

- Subject: {topic_data['subjectName']}
- Class/Grade: {topic_data['classGrade']}
- Topic: {topic_data['sectionName']}
- Difficulty Level: {topic_data['difficulty']}
- Bloom's Taxonomy Level: {topic_data['bloomLevel']}
- Intelligence Type: {topic_data['intelligenceType']}
- Intelligence SubType: {topic_data.get('intelligenceSubType', 'General')}

{note_context}

Additional Instructions: {topic_data['additionalInstructions']}

{feedback_context}

🔵 Strict Requirements:
1. Match exactly the specified difficulty and Bloom's level.
2. Test deep conceptual understanding, not rote memorization (unless instructed).
3. Use technical language appropriate for Class {topic_data['classGrade']} level.
4. Follow the {topic_data['questionType']} format precisely.
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

def create_pdf(questions, filename, subject_name, class_grade):
    # Create PDF in memory
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Define custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor='#2c3e50'  # Dark blue color
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=20,
        textColor='#34495e'  # Slightly lighter blue
    )
    
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        textColor='#2c3e50',
        backColor='#f8f9fa',  # Light gray background
        borderPadding=5,
        borderColor='#dee2e6',
        borderWidth=1
    )
    
    option_style = ParagraphStyle(
        'OptionStyle',
        parent=styles['Normal'],
        fontSize=11,
        leftIndent=20,
        spaceAfter=5,
        textColor='#495057'
    )
    
    answer_style = ParagraphStyle(
        'AnswerStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=10,
        textColor='#28a745',  # Green color for answers
        backColor='#e8f5e9',  # Light green background
        borderPadding=5,
        borderColor='#c8e6c9',
        borderWidth=1
    )
    
    explanation_style = ParagraphStyle(
        'ExplanationStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=20,
        textColor='#6c757d',
        leftIndent=20
    )
    
    # Add title and paper details
    story.append(Paragraph("QUESTION PAPER", title_style))
    
    # Add paper details
    details = [
        f"<b>Class:</b> {class_grade}",
        f"<b>Subject:</b> {subject_name}",
        f"<b>Total Questions:</b> {sum(len(topic['questions']) for topic in questions)}"
    ]
    
    for detail in details:
        story.append(Paragraph(detail, styles['Normal']))
        story.append(Spacer(1, 5))
    
    story.append(Spacer(1, 20))
    
    # Add questions
    for i, topic in enumerate(questions, 1):
        # Add topic header
        story.append(Paragraph(f"Topic {i}: {topic['topic']}", header_style))
        story.append(Spacer(1, 10))
        
        # Add questions
        for j, q in enumerate(topic['questions'], 1):
            # Question text
            story.append(Paragraph(f"Q{j}. {q['question']}", question_style))
            
            # Options (if MCQ)
            if 'options' in q:
                for opt in q['options']:
                    story.append(Paragraph(f"• {opt}", option_style))
            
            # Answer
            story.append(Paragraph(f"<b>Answer:</b> {q['answer']}", answer_style))
            
            # Explanation
            story.append(Paragraph(f"<b>Explanation:</b> {q['explanation']}", explanation_style))
            
            # Add spacing between questions
            story.append(Spacer(1, 15))
    
    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer

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
        'subject': topic_data['subjectName'],
        'class': topic_data['classGrade'],
        'topic': topic_data['sectionName'],
        'type': topic_data['questionType'],
        'difficulty': topic_data['difficulty'],
        'bloom': topic_data['bloomLevel'],
        'intelligence': topic_data['intelligenceType']
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

def generate_questions_for_topic(topic_data, previous_paper_id=None):
    """Generate questions for a single topic with caching"""
    try:
        print(f"\nGenerating questions for topic: {topic_data['sectionName']}")
        print(f"Topic data: {json.dumps(topic_data, indent=2)}")

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

        print("Generating prompt...")
        prompt = generate_question_prompt(topic_data, previous_paper_id)
        print("Generated prompt. Calling OpenAI API...")

        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert educational question generator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            print("Received response from OpenAI")
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            raise

        try:
            print("Parsing OpenAI response...")
            questions = json.loads(response.choices[0].message.content)
            print(f"Successfully parsed questions: {json.dumps(questions, indent=2)}")
        except json.JSONDecodeError as e:
            print(f"Error parsing OpenAI response: {str(e)}")
            print(f"Raw response content: {response.choices[0].message.content}")
            raise
        
        # Cache the results
        cache_data = {
            'cache_key': cache_key,
            'questions': questions['questions'],
            'created_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
        }
        papers_collection.insert_one(cache_data)
        print("Cached the generated questions")
        
        return {
            'topic': topic_data['sectionName'],
            'questions': questions['questions'],
            'cached': False
        }
    except Exception as e:
        print(f"Error generating questions for topic {topic_data['sectionName']}: {str(e)}")
        print("Full error details:", e.__dict__)
        raise

@app.route('/api/generate-questions', methods=['POST'])
def generate_questions():
    try:
        print("Received request at /api/generate-questions")
        data = request.json
        print("Request data:", json.dumps(data, indent=2))

        # Validate required fields
        required_fields = ['subjectName', 'classGrade', 'topics']
        for field in required_fields:
            if field not in data:
                print(f"Missing required field: {field}")
                return jsonify({
                    'success': False,
                    'error': f"Missing required field: {field}"
                }), 400

        # Validate topic fields
        required_topic_fields = ['sectionName', 'questionType', 'difficulty', 'bloomLevel', 'intelligenceType', 'numQuestions']
        for i, topic in enumerate(data['topics']):
            for field in required_topic_fields:
                if not topic.get(field):
                    print(f"Missing or empty required field '{field}' in topic {i+1}")
                    return jsonify({
                        'success': False,
                        'error': f"Missing or empty required field '{field}' in topic {i+1}"
                    }), 400

        # Save request to MongoDB
        data['created_at'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
        request_id = requests_collection.insert_one(data).inserted_id
        print(f"Saved request to MongoDB with ID: {request_id}")

        # Generate questions for all topics
        all_questions = []
        for topic in data['topics']:
            topic_data = {
                **topic,
                'subjectName': data['subjectName'],
                'classGrade': data['classGrade']
            }
            questions = generate_questions_for_topic(topic_data, data.get('previous_paper_id'))
            all_questions.append(questions)
        
        print(f"Successfully generated questions for all topics")

        # Save generated questions to MongoDB
        paper_data = {
            'request_id': str(request_id),
            'questions': all_questions,
            'created_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
            'previous_paper_id': data.get('previous_paper_id')
        }
        paper_id = papers_collection.insert_one(paper_data).inserted_id
        print(f"Saved generated questions to MongoDB with ID: {paper_id}")

        # Generate PDF and upload to S3
        try:
            pdf_filename = f"question_paper_{paper_id}.pdf"
            pdf_buffer = create_pdf(all_questions, pdf_filename, data['subjectName'], data['classGrade'])
            print("Successfully generated PDF")

            # Upload to S3
            s3_client.upload_fileobj(
                pdf_buffer,
                S3_BUCKET,
                pdf_filename,
                ExtraArgs={'ContentType': 'application/pdf'}
            )
            print(f"Successfully uploaded PDF to S3: {pdf_filename}")
            
            # Generate pre-signed URL with longer expiration
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': pdf_filename
                },
                ExpiresIn=3600  # URL expires in 1 hour
            )
            print(f"Generated pre-signed URL for PDF: {url}")

            return jsonify({
                'success': True,
                'paper_id': str(paper_id),
                'questions': all_questions,
                'pdf_url': url
            })

        except Exception as e:
            print(f"Error with PDF generation or S3 upload: {e}")
            return jsonify({
                'success': False,
                'error': f"Error generating PDF: {str(e)}"
            }), 500

    except Exception as e:
        print("Error in /api/generate-questions:", str(e))
        print("Full error details:", e.__dict__)
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
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({
                'success': False,
                'error': 'Only PDF files are allowed'
            }), 400

        # Generate unique filename
        filename = f"notes/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        
        # Upload to S3
        s3_client.upload_fileobj(
            file,
            NOTES_BUCKET,
            filename,
            ExtraArgs={
                'ContentType': 'application/pdf'
            }
        )

        # Generate pre-signed URL for download
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': NOTES_BUCKET,
                'Key': filename
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )

        # Save note metadata to MongoDB
        note_data = {
            'filename': filename,
            'original_name': file.filename,
            'uploaded_at': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
            's3_url': url
        }
        notes_collection = db['notes']
        note_id = notes_collection.insert_one(note_data).inserted_id

        return jsonify({
            'success': True,
            'note_id': str(note_id),
            'filename': file.filename,
            'url': url
        })

    except Exception as e:
        print(f"Error uploading note: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/notes', methods=['GET'])
def get_notes():
    try:
        notes = list(db['notes'].find(
            {},
            {'_id': 1, 'original_name': 1, 'uploaded_at': 1, 'text_preview': 1}
        ).sort('uploaded_at', -1))
        
        for note in notes:
            note['_id'] = str(note['_id'])
            # Generate fresh pre-signed URL
            note['url'] = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': NOTES_BUCKET,
                    'Key': note['filename']
                },
                ExpiresIn=3600
            )
        
        return jsonify({
            'success': True,
            'notes': notes
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
        debug=False  # Run in production mode
    )