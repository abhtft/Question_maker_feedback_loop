import os
import json
import base64
import re
import logging
import uuid
import email
from datetime import datetime
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv

# Load env variables (useful for local testing)
load_dotenv()

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import backend modules
import mylang4
from langchain_community.vectorstores import FAISS
from Utility.pdfmaker import CreatePDF


"""
#testing function

python qplambda.py



"""

# ----------------------------------------------------
# AWS Clients and Environment Configurations
# ----------------------------------------------------
region_name = os.getenv('AWS_REGION', 'us-east-1')

# Initialize S3 Client
try:
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    if aws_access_key and aws_secret_key:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region_name
        )
    else:
        s3_client = boto3.client('s3', region_name=region_name)
    logger.info("AWS S3 Connection Successful!")
except Exception as e:
    logger.error(f"AWS S3 Connection Error: {e}")
    s3_client = None

S3_BUCKET = os.getenv('S3_BUCKET_NAME')
NOTES_BUCKET = os.getenv('NOTES_BUCKET_NAME')

# Initialize DynamoDB Resource
try:
    if aws_access_key and aws_secret_key:
        dynamodb = boto3.resource(
            'dynamodb',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region_name
        )
    else:
        dynamodb = boto3.resource('dynamodb', region_name=region_name)
        
    requests_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_REQUESTS', 'question_requests'))
    papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))
    notes_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NOTES', 'notes'))
    logger.info("AWS DynamoDB Resource Initialization Successful!")
except Exception as e:
    logger.error(f"AWS DynamoDB Resource Initialization Error: {e}")
    dynamodb = None
    requests_table = None
    papers_table = None
    notes_table = None

# ----------------------------------------------------
# Helper Utilities
# ----------------------------------------------------
def convert_floats_to_decimals(obj):
    """Recursively convert float values to Decimal for DynamoDB serialization."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(x) for x in obj]
    return obj

def make_response(status_code, body_dict):
    """Generate a standard API Gateway proxy response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(body_dict)
    }

def parse_multipart(body_bytes, content_type):
    """Parses multipart/form-data request body without using deprecated CGI module."""
    # Build MIME message structure from raw multipart boundary content
    msg = email.message_from_bytes(b"Content-Type: " + content_type.encode('utf-8') + b"\r\n\r\n" + body_bytes)
    files = {}
    form_data = {}
    
    if msg.is_multipart():
        for part in msg.walk():
            # Skip parent container
            if part.get_content_type() == 'multipart/form-data':
                continue
            
            disposition = part.get('Content-Disposition', '')
            if not disposition:
                continue
                
            name_match = re.search(r'name="([^"]+)"', disposition)
            if not name_match:
                continue
            name = name_match.group(1)
            
            # Check if part contains a file
            filename_match = re.search(r'filename="([^"]+)"', disposition)
            if filename_match:
                filename = filename_match.group(1)
                file_content = part.get_payload(decode=True)
                files[name] = {
                    'filename': filename,
                    'content': file_content,
                    'content_type': part.get_content_type()
                }
            else:
                text_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                form_data[name] = text_content
                
    return files, form_data

def get_s3_key_for_note(note_id):
    """Retrieve S3 storage path for note from DynamoDB, falling back to base64 decode."""
    if notes_table is not None:
        try:
            response = notes_table.get_item(Key={'note_id': note_id})
            if 'Item' in response:
                return response['Item'].get('filename')
        except Exception as e:
            logger.error(f"Error querying DynamoDB for note {note_id}: {e}")
            
    # Fallback: Check if note_id contains base64 encoded S3 path
    try:
        decoded = base64.urlsafe_b64decode(note_id.encode('utf-8')).decode('utf-8')
        if decoded.startswith('notes/'):
            return decoded
    except Exception:
        pass
        
    # If the note_id itself matches the key structure
    if note_id.startswith('notes/'):
        return note_id
        
    return None

# ----------------------------------------------------
# Endpoint Action Handlers
# ----------------------------------------------------
def handle_generate_questions(event):
    body_str = event.get('body', '')
    if event.get('isBase64Encoded', False):
        body_str = base64.b64decode(body_str).decode('utf-8')
        
    try:
        data = json.loads(body_str)
    except Exception as e:
        return make_response(400, {'success': False, 'error': f"Invalid JSON body: {str(e)}"})
        
    # Validate required parameters
    required_fields = ['email', 'subjectName', 'classGrade', 'topics']
    for field in required_fields:
        if field not in data:
            return make_response(400, {'success': False, 'error': f"Missing required field: {field}"})
            
    # Assign created_at timestamp
    created_at = datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
    data['created_at'] = created_at
    
    # Save Request to DynamoDB
    request_id = str(uuid.uuid4())
    if requests_table is not None:
        try:
            item = {
                'request_id': request_id,
                **data
            }
            requests_table.put_item(Item=convert_floats_to_decimals(item))
            logger.info(f"Saved request {request_id} to DynamoDB.")
        except Exception as e:
            logger.error(f"Failed to write request log to DynamoDB: {e}")
            
    # Determine noteId from topics to load S3-persisted vectorstore
    note_id = None
    for topic in data.get('topics', []):
        if topic.get('noteId'):
            note_id = topic.get('noteId')
            break
            
    vectorstore = None
    if note_id and s3_client is not None:
        s3_key_prefix = f"vectorstores/{note_id}"
        vectorstore_path = f"/tmp/vectorstores/{note_id}"
        os.makedirs(vectorstore_path, exist_ok=True)
        
        try:
            logger.info(f"Downloading vectorstore files from S3 for note: {note_id}")
            s3_client.download_file(NOTES_BUCKET, f"{s3_key_prefix}/index.faiss", os.path.join(vectorstore_path, 'index.faiss'))
            s3_client.download_file(NOTES_BUCKET, f"{s3_key_prefix}/index.pkl", os.path.join(vectorstore_path, 'index.pkl'))
            
            # Load local FAISS vectorstore
            vectorstore = FAISS.load_local(
                vectorstore_path, 
                mylang4.document_processor.embeddings, 
                allow_dangerous_deserialization=True
            )
            logger.info(f"Successfully loaded vectorstore from S3 files under {vectorstore_path}")
        except Exception as e:
            logger.error(f"Failed to load vectorstore index from S3: {e}")
            
    # Generate Questions for Topics
    all_questions = []
    for topic in data['topics']:
        topic_data = {
            **topic,
            'subjectName': data['subjectName'],
            'classGrade': data['classGrade']
        }
        
        try:
            num_qs = int(topic.get('numQuestions', 1))
        except ValueError:
            num_qs = 1
            
        batch_size = 5
        topic_questions = []
        
        for i in range(0, num_qs, batch_size):
            current_batch = min(batch_size, num_qs - i)
            batch_data = {**topic_data, 'numQuestions': current_batch}
            
            questions = mylang4.question_generator.generate_questions(
                batch_data, 
                vectorstore, 
                mylang4.question_verifier
            )
            
            # Handle list/dict returned structure
            if isinstance(questions['questions'], dict) and 'questions' in questions['questions']:
                topic_questions.extend(questions['questions']['questions'])
            elif isinstance(questions['questions'], list):
                topic_questions.extend(questions['questions'])
            else:
                logger.error(f"Unexpected questions structure: {type(questions['questions'])}")
                if isinstance(questions['questions'], dict):
                    topic_questions.extend(questions['questions'].get('questions', []))
                    
            if 'verification_result' in questions:
                logger.info(f"Question quality verdict for '{topic.get('sectionName', '')}': {questions['verification_result']['overall_verdict']}")
                
        all_questions.append({
            'topic': topic.get('sectionName', ''),
            'questions': topic_questions,
            'cached': False
        })
        
    paper_id = str(uuid.uuid4())
    paper_data = {
        'paper_id': paper_id,
        'request_id': request_id,
        'questions': all_questions,
        'created_at': datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
        'previous_paper_id': data.get('previous_paper_id')
    }
    
    # Save Generated Paper to DynamoDB
    if papers_table is not None:
        try:
            papers_table.put_item(Item=convert_floats_to_decimals(paper_data))
            logger.info(f"Saved paper {paper_id} to DynamoDB.")
        except Exception as e:
            logger.error(f"Failed to write paper log to DynamoDB: {e}")
            
    # Generate PDF Document in Memory
    pdf_filename = f"question_paper_{paper_id}.pdf"
    pdf_buffer = CreatePDF.generate(
        all_questions,
        pdf_filename,
        class_grade=data['classGrade'],
        subject_name=data['subjectName']
    )
    
    pdf_url = ""
    # Upload PDF to S3
    if s3_client is not None and S3_BUCKET:
        try:
            s3_client.upload_fileobj(
                pdf_buffer,
                S3_BUCKET,
                pdf_filename,
                ExtraArgs={'ContentType': 'application/pdf'}
            )
            
            # Generate Pre-Signed S3 download URL
            pdf_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET, 'Key': pdf_filename},
                ExpiresIn=3600
            )
            logger.info(f"Successfully uploaded PDF to S3: {pdf_filename}")
        except Exception as e:
            logger.error(f"Failed to upload PDF to S3: {e}")
            
    # Trigger Google Form webhook
    google_form_url = None
    google_form_webhook = os.getenv('GOOGLE_FORM_WEBHOOK_URL')
    if google_form_webhook:
        try:
            response = requests.post(
                google_form_webhook,
                json={
                    "email": data['email'],
                    "paper_name": data['subjectName'],
                    "class_grade": data['classGrade'],
                    "all_questions": all_questions,
                },
                timeout=5
            )
            response.raise_for_status()
            result = response.json()
            google_form_url = result.get("publicUrl")
            logger.info(f"Google Form webhook response: {response.text}")
        except Exception as e:
            logger.error(f"Error triggering Google Form webhook: {e}")
            
    # Trigger n8n webhook
    n8n_webhook = os.getenv('N8N_WEBHOOK_URL')
    if n8n_webhook:
        try:
            requests.post(
                n8n_webhook,
                json={
                    "email": data['email'],
                    "paper_name": data['subjectName'],
                    "class_grade": data['classGrade'],
                    "all_questions": all_questions,
                    "topics": data['topics'],
                    "num_questions": sum(int(t.get('numQuestions', 1)) for t in data['topics']),
                    "google_form_url": google_form_url,
                    "pdf_url": pdf_url,
                },
                timeout=5
            )
            logger.info("n8n webhook triggered successfully")
        except Exception as e:
            logger.error(f"Error triggering n8n webhook: {e}")
            
    # Clean up local /tmp FAISS vectorstore
    if note_id and os.path.exists(f"/tmp/vectorstores/{note_id}"):
        try:
            import shutil
            shutil.rmtree(f"/tmp/vectorstores/{note_id}")
        except Exception as e:
            logger.warning(f"Failed to delete temp vectorstore directory: {e}")
            
    return make_response(200, {
        'success': True,
        'paper_id': paper_id,
        'questions': all_questions,
        'pdf_url': pdf_url
    })

def handle_download_pdf(paper_id):
    if s3_client is None or not S3_BUCKET:
        return make_response(500, {'success': False, 'error': 'S3 client not initialized'})
        
    try:
        filename = f"question_paper_{paper_id}.pdf"
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': filename
            },
            ExpiresIn=3600
        )
        return make_response(200, {
            'success': True,
            'url': url
        })
    except Exception as e:
        logger.error(f"Failed to generate download url for paper {paper_id}: {e}")
        return make_response(500, {'success': False, 'error': str(e)})

def handle_upload_note(event):
    if s3_client is None or not NOTES_BUCKET:
        return make_response(500, {'success': False, 'error': 'S3 client not initialized'})
        
    try:
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body_bytes = base64.b64decode(body)
        else:
            body_bytes = body.encode('utf-8') if isinstance(body, str) else body
            
        headers = event.get('headers', {})
        headers_lower = {k.lower(): v for k, v in headers.items()}
        content_type = headers_lower.get('content-type', '')
        
        if 'multipart/form-data' not in content_type:
            return make_response(400, {'success': False, 'error': 'Content-Type must be multipart/form-data'})
            
        files, form_data = parse_multipart(body_bytes, content_type)
        
        if 'file' not in files:
            return make_response(400, {'success': False, 'error': 'No file provided in form-data'})
            
        file_info = files['file']
        filename = file_info['filename']
        file_content = file_info['content']
        
        if not filename.lower().endswith('.pdf'):
            return make_response(400, {'success': False, 'error': 'Only PDF files are allowed'})
            
        # Create S3 Key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3_filename = f"notes/{timestamp}_{filename}"
        
        # Upload binary file to S3
        s3_client.put_object(
            Bucket=NOTES_BUCKET,
            Key=s3_filename,
            Body=file_content,
            ContentType='application/pdf'
        )
        logger.info(f"File uploaded to S3: {s3_filename}")
        
        note_id = None
        # Save note metadata to DynamoDB
        if notes_table is not None:
            try:
                note_id = str(uuid.uuid4())
                note_data = {
                    'note_id': note_id,
                    'filename': s3_filename,
                    'original_name': filename,
                    'uploaded_at': datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S'),
                    's3_url': f"s3://{NOTES_BUCKET}/{s3_filename}"
                }
                notes_table.put_item(Item=note_data)
                logger.info(f"Saved note {note_id} metadata to DynamoDB.")
            except Exception as e:
                logger.error(f"Error saving note metadata to DynamoDB: {e}")
                note_id = None
                
        if not note_id:
            # Fallback: base64-encode the S3 key so we can retrieve it stateless-ly
            note_id = base64.urlsafe_b64encode(s3_filename.encode('utf-8')).decode('utf-8')
            
        return make_response(200, {
            'success': True,
            'note_id': note_id,
            'filename': filename
        })
    except Exception as e:
        logger.error(f"Error in handle_upload_note: {e}", exc_info=True)
        return make_response(500, {'success': False, 'error': str(e)})

def handle_analyse_note(event):
    if s3_client is None or not NOTES_BUCKET:
        return make_response(500, {'success': False, 'error': 'S3 client not initialized'})
        
    try:
        body_str = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body_str = base64.b64decode(body_str).decode('utf-8')
            
        try:
            body_data = json.loads(body_str)
        except Exception:
            return make_response(400, {'success': False, 'error': 'Invalid JSON body'})
            
        note_id = body_data.get('note_id')
        if not note_id:
            return make_response(400, {'success': False, 'error': 'note_id is required'})
            
        s3_filename = get_s3_key_for_note(note_id)
        if not s3_filename:
            return make_response(404, {'success': False, 'error': f'Note metadata not found for ID: {note_id}'})
            
        local_pdf_path = f"/tmp/{os.path.basename(s3_filename)}"
        logger.info(f"Downloading PDF from S3: {s3_filename} to {local_pdf_path}")
        s3_client.download_file(NOTES_BUCKET, s3_filename, local_pdf_path)
        
        # Analyze Document
        vectorstore_path = f"/tmp/vectorstores/{note_id}"
        os.makedirs(vectorstore_path, exist_ok=True)
        
        logger.info("Processing document chunks using mylang4...")
        vectorstore, chunks = mylang4.document_processor.process_uploaded_document(
            local_pdf_path, 
            persist_directory=vectorstore_path
        )
        
        # Upload FAISS files to S3
        logger.info(f"Uploading created FAISS vectorstore to S3: {note_id}")
        for file_name in ['index.faiss', 'index.pkl']:
            local_file = os.path.join(vectorstore_path, file_name)
            s3_key = f"vectorstores/{note_id}/{file_name}"
            s3_client.upload_file(local_file, NOTES_BUCKET, s3_key)
            
        # Clean up local PDF and FAISS files
        if os.path.exists(local_pdf_path):
            os.remove(local_pdf_path)
        if os.path.exists(vectorstore_path):
            import shutil
            shutil.rmtree(vectorstore_path)
            
        return make_response(200, {'success': True})
    except Exception as e:
        logger.error(f"Error in handle_analyse_note: {e}", exc_info=True)
        return make_response(500, {'success': False, 'error': str(e)})

def handle_mylang_test(event):
    try:
        body_str = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body_str = base64.b64decode(body_str).decode('utf-8')
            
        data = json.loads(body_str) if body_str else None
        if not data:
            data = {
                "numQuestions": 2,
                "questionType": "MCQ",
                "subjectName": "Mathematics",
                "classGrade": "10th",
                "sectionName": "Algebra",
                "difficulty": "Medium",
                "bloomLevel": "Understand",
                "additionalInstructions": "Focus on quadratic equations"
            }
            
        logger.info(f"Testing mylang4 with payload: {data}")
        out = mylang4.question_generator.generate_questions(data, None, mylang4.question_verifier)
        return make_response(200, {'success': True, 'output': out})
    except Exception as e:
        logger.error(f"Error in handle_mylang_test: {e}")
        return make_response(500, {'success': False, 'error': str(e)})

def handle_mylang_test_get(event):
    try:
        data = {
            "numQuestions": 1,
            "questionType": "MCQ",
            "subjectName": "Mathematics",
            "classGrade": "10th",
            "sectionName": "Algebra",
            "difficulty": "Medium",
            "bloomLevel": "Understand",
            "additionalInstructions": "Focus on quadratic equations"
        }
        logger.info(f"Testing mylang4 GET with payload: {data}")
        out = mylang4.question_generator.generate_questions(data, None, mylang4.question_verifier)
        return make_response(200, {'success': True, 'output': out})
    except Exception as e:
        logger.error(f"Error in handle_mylang_test_get: {e}")
        return make_response(500, {'success': False, 'error': str(e)})

# ----------------------------------------------------
# Main Lambda Entry Handler
# ----------------------------------------------------
def lambda_handler(event, context):
    logger.info(f"Received API Gateway event: {json.dumps(event)}")
    
    # Resolve Path and HTTP Method from event structure (v1 and v2 compatible)
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('path') or event.get('rawPath') or event.get('requestContext', {}).get('http', {}).get('path', '/')
    
    http_method = http_method.upper()
    
    # Process CORS OPTIONS Preflight
    if http_method == 'OPTIONS':
        return make_response(200, {"message": "CORS preflight successful"})
        
    try:
        if path == '/api/generate-questions' and http_method == 'POST':
            return handle_generate_questions(event)
            
        elif path.startswith('/api/download-pdf/') and http_method == 'GET':
            match = re.match(r'^/api/download-pdf/([^/]+)$', path)
            if match:
                paper_id = match.group(1)
                return handle_download_pdf(paper_id)
            else:
                return make_response(400, {"success": False, "error": "Invalid request parameters"})
                
        elif path == '/api/upload-note' and http_method == 'POST':
            return handle_upload_note(event)
            
        elif path == '/api/analyse-note' and http_method == 'POST':
            return handle_analyse_note(event)
            
        elif path == '/api/mylangtest' and http_method == 'POST':
            return handle_mylang_test(event)
            
        elif path == '/api/mylangtest-get' and http_method == 'GET':
            return handle_mylang_test_get(event)
            
        else:
            return make_response(404, {"success": False, "error": f"API route not found: {http_method} {path}"})
            
    except Exception as e:
        logger.error(f"Internal Lambda execution error: {str(e)}", exc_info=True)
        return make_response(500, {"success": False, "error": str(e)})
