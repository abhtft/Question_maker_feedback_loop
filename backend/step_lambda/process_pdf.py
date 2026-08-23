import os
import sys
import boto3
from dotenv import load_dotenv

load_dotenv()

# Setup sys.path dynamically to import generator from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_path = os.path.join(project_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from generator import generator

region_name = os.getenv('AWS_REGION', 'us-east-1')
s3_client = boto3.client('s3', region_name=region_name)
dynamodb = boto3.resource('dynamodb', region_name=region_name)
papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))
notes_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NOTES', 'notes'))
NOTES_BUCKET = os.getenv('NOTES_BUCKET_NAME')

def update_status(task_id, status):
    """Utility to update DynamoDB status."""
    try:
        papers_table.update_item(
            Key={'paper_id': task_id},
            UpdateExpression="SET #s = :status",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':status': status}
        )
    except Exception as e:
        print(f"Failed to update status to {status} in DynamoDB: {e}")

def get_s3_key_for_note(note_id):
    """Retrieve S3 storage path for note from DynamoDB."""
    try:
        response = notes_table.get_item(Key={'note_id': note_id})
        if 'Item' in response:
            return response['Item'].get('filename')
    except Exception as e:
        print(f"Error querying DynamoDB for note {note_id}: {e}")
    
    # Fallback/Direct match
    if note_id.startswith('notes/'):
        return note_id
    return None

def handler(event, context):
    """
    AWS Lambda Step Functions Task.
    Action: Chunk & index PDF using FAISS, uploading the output files back to S3.
    """
    task_id = event['task_id']
    
    # Extract note_id from topics
    note_id = None
    for topic in event.get('topics', []):
        if topic.get('noteId'):
            note_id = topic.get('noteId')
            break
            
    if not note_id:
        # Step Functions routing checks this, but if it somehow invokes here, just bypass
        return event

    update_status(task_id, 'PROCESSING_PDF')

    s3_filename = get_s3_key_for_note(note_id)
    if not s3_filename:
        raise ValueError(f"Note key not found in metadata database for ID: {note_id}")

    local_pdf_path = f"/tmp/{os.path.basename(s3_filename)}"
    print(f"Downloading PDF from S3: {s3_filename} to {local_pdf_path}")
    
    try:
        s3_client.download_file(NOTES_BUCKET, s3_filename, local_pdf_path)
        
        # Build local FAISS vectorstore
        vectorstore_path = f"/tmp/vectorstores/{note_id}"
        os.makedirs(vectorstore_path, exist_ok=True)
        
        print("Vectorizing document...")
        vectorstore, chunks = generator.document_processor.process_uploaded_document(
            local_pdf_path, 
            persist_directory=vectorstore_path
        )
        
        # Upload FAISS files to S3
        print(f"Uploading created FAISS vectorstore to S3 for note: {note_id}")
        for file_name in ['index.faiss', 'index.pkl']:
            local_file = os.path.join(vectorstore_path, file_name)
            s3_key = f"vectorstores/{note_id}/{file_name}"
            s3_client.upload_file(local_file, NOTES_BUCKET, s3_key)
            
        print("PDF Processing successful.")
        
    except Exception as e:
        update_status(task_id, f"FAILED (PDF processing error: {str(e)})")
        raise e
        
    finally:
        # Clean up temporary storage to avoid resource leakage in reused execution contexts
        if os.path.exists(local_pdf_path):
            os.remove(local_pdf_path)
        if os.path.exists(f"/tmp/vectorstores/{note_id}"):
            import shutil
            shutil.rmtree(f"/tmp/vectorstores/{note_id}")

    # Pass the note_id in output state so subsequent tasks can find it
    event['note_id'] = note_id
    return event
