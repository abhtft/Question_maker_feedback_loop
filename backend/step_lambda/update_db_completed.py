import os
import sys
import boto3
from decimal import Decimal
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

def convert_floats_to_decimals(obj):
    """Recursively convert float values to Decimal for DynamoDB serialization."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(x) for x in obj]
    return obj

def handler(event, context):
    """
    AWS Lambda Step Functions Task.
    Action: Finalize database records with generated questions and output asset URLs.
    """
    task_id = event['task_id']
    questions = event['generated_questions']
    pdf_url = event['pdf_url']
    google_form_url = event.get('google_form_url')
    attempts = event.get('attempts_used', 1)

    print(f"Finalizing database record for task {task_id} as COMPLETED.")
    
    # Structure final paper details
    completed_fields = {
        'status': 'COMPLETED',
        'questions': questions,
        'pdf_url': pdf_url,
        'google_form_url': google_form_url,
        'attempts_used': attempts
    }

    # Convert nested float decimals
    completed_fields_decimal = convert_floats_to_decimals(completed_fields)

    # Perform updates in DynamoDB
    try:
        papers_table.update_item(
            Key={'paper_id': task_id},
            UpdateExpression="SET #s = :status, questions = :questions, pdf_url = :pdf_url, google_form_url = :google_form_url, attempts_used = :attempts",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': completed_fields_decimal['status'],
                ':questions': completed_fields_decimal['questions'],
                ':pdf_url': completed_fields_decimal['pdf_url'],
                ':google_form_url': completed_fields_decimal['google_form_url'],
                ':attempts': completed_fields_decimal['attempts_used']
            }
        )
        print("Database record successfully updated.")
    except Exception as e:
        print(f"Error finalizing database update: {e}")
        raise e

    return event
