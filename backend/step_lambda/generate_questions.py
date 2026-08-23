import os
import sys
import boto3
import gc
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS

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

def handler(event, context):
    """
    AWS Lambda Step Functions Task.
    Action: Download FAISS context index from S3, run generation, and compile quality scoring.
    """
    task_id = event['task_id']
    note_id = event.get('note_id')
    attempts = event.get('attempts_used', 0) + 1
    event['attempts_used'] = attempts

    update_status(task_id, f'GENERATING_QUESTIONS (Attempt {attempts})')

    # Load vectorstore from S3 if note_id exists
    vectorstore = None
    if note_id and s3_client is not None:
        s3_key_prefix = f"vectorstores/{note_id}"
        vectorstore_path = f"/tmp/vectorstores/{note_id}"
        os.makedirs(vectorstore_path, exist_ok=True)
        
        try:
            print(f"Downloading vector store index from S3 for note: {note_id}")
            s3_client.download_file(NOTES_BUCKET, f"{s3_key_prefix}/index.faiss", os.path.join(vectorstore_path, 'index.faiss'))
            s3_client.download_file(NOTES_BUCKET, f"{s3_key_prefix}/index.pkl", os.path.join(vectorstore_path, 'index.pkl'))
            
            # Load local FAISS vectorstore
            vectorstore = FAISS.load_local(
                vectorstore_path, 
                generator.document_processor.embeddings, 
                allow_dangerous_deserialization=True
            )
            print("Successfully loaded vector store.")
        except Exception as e:
            print(f"Failed to load vector store from S3: {e}")
            # Continue without context if vector store fails to load

    # Generate questions for each topic
    all_questions = []
    topic_verifications = []
    
    try:
        for topic in event['topics']:
            topic_data = {
                **topic,
                'subjectName': event['subjectName'],
                'classGrade': event['classGrade']
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
                
                print(f"Generating questions batch for topic: '{topic.get('sectionName')}'")
                res = generator.question_generator.generate_questions(
                    batch_data, 
                    vectorstore, 
                    generator.question_verifier
                )
                
                # Handle nested dict or list output format
                if isinstance(res['questions'], dict) and 'questions' in res['questions']:
                    topic_questions.extend(res['questions']['questions'])
                elif isinstance(res['questions'], list):
                    topic_questions.extend(res['questions'])
                else:
                    print(f"Unexpected questions structure type: {type(res['questions'])}")
                    if isinstance(res['questions'], dict):
                        topic_questions.extend(res['questions'].get('questions', []))
                
                # Capture verification result of this batch
                if 'verification_result' in res:
                    topic_verifications.append(res['verification_result'])
                    
                gc.collect()
                
            all_questions.append({
                'topic': topic.get('sectionName', ''),
                'questions': topic_questions,
                'cached': False
            })
            
    except Exception as e:
        update_status(task_id, f"FAILED (Generation error: {str(e)})")
        raise e
        
    finally:
        # Clean up local FAISS index path
        if note_id and os.path.exists(f"/tmp/vectorstores/{note_id}"):
            try:
                import shutil
                shutil.rmtree(f"/tmp/vectorstores/{note_id}")
            except Exception as e:
                print(f"Failed to remove vector store directory: {e}")

    # Determine overall quality verification verdict across all batches
    overall_verdict = "Pass"
    for verdict in topic_verifications:
        if verdict.get('overall_verdict') != 'Pass':
            overall_verdict = "Fail"
            break

    # Save output to state payload
    event['generated_questions'] = all_questions
    event['verification_result'] = {
        'overall_verdict': overall_verdict,
        'topic_details': topic_verifications
    }

    if overall_verdict == "Fail":
        update_status(task_id, f"VERIFICATION_FAILED (Attempt {attempts} of 3)")
    else:
        update_status(task_id, 'VERIFICATION_PASSED')

    return event
