import os
import sys
import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

# Setup sys.path dynamically
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_path = os.path.join(project_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

region_name = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=region_name)
papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))

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
    Action: Send payloads to Google Form webhook and n8n email notifier.
    """
    task_id = event['task_id']
    all_questions = event['generated_questions']
    pdf_url = event['pdf_url']

    update_status(task_id, 'SENDING_NOTIFICATIONS')

    # 1. Trigger Google Form quiz generation
    google_form_url = None
    google_form_webhook = os.getenv('GOOGLE_FORM_WEBHOOK_URL')
    if google_form_webhook:
        try:
            print("Triggering Google Form webhook...")
            response = requests.post(
                google_form_webhook,
                json={
                    "email": event['email'],
                    "paper_name": event['subjectName'],
                    "class_grade": event['classGrade'],
                    "all_questions": all_questions,
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            google_form_url = result.get("publicUrl")
            print(f"Successfully generated Google Form quiz: {google_form_url}")
        except Exception as e:
            print(f"Error triggering Google Form webhook: {e}")
            # Continue even if quiz creation fails, so that we still send the PDF
    
    # 2. Trigger n8n notifier webhook (email delivery)
    n8n_webhook = os.getenv('N8N_WEBHOOK_URL')
    if n8n_webhook:
        try:
            print("Triggering n8n notifier webhook...")
            total_questions = sum(int(t.get('numQuestions', 1)) for t in event['topics'])
            requests.post(
                n8n_webhook,
                json={
                    "email": event['email'],
                    "paper_name": event['subjectName'],
                    "class_grade": event['classGrade'],
                    "all_questions": all_questions,
                    "topics": event['topics'],
                    "num_questions": total_questions,
                    "google_form_url": google_form_url,
                    "pdf_url": pdf_url,
                },
                timeout=10
            )
            print("n8n notifier triggered successfully.")
        except Exception as e:
            print(f"Error triggering n8n webhook: {e}")

    event['google_form_url'] = google_form_url
    return event
