import os
import sys
import boto3
from dotenv import load_dotenv

load_dotenv()

# Setup sys.path dynamically to import Utility and generator from backend
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_path = os.path.join(project_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Utility.pdfmaker import CreatePDF

region_name = os.getenv('AWS_REGION', 'us-east-1')
s3_client = boto3.client('s3', region_name=region_name)
dynamodb = boto3.resource('dynamodb', region_name=region_name)
papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))
S3_BUCKET = os.getenv('S3_BUCKET_NAME')

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
    Action: Compile ReportLab PDF from questions and upload it to AWS S3.
    """
    task_id = event['task_id']
    all_questions = event['generated_questions']

    update_status(task_id, 'COMPILING_PDF')

    pdf_filename = f"question_paper_{task_id}.pdf"
    
    try:
        print(f"Compiling PDF: {pdf_filename}")
        pdf_buffer = CreatePDF.generate(
            all_questions,
            pdf_filename,
            class_grade=event['classGrade'],
            subject_name=event['subjectName']
        )
        
        # Upload binary file to S3
        print(f"Uploading PDF file to S3 bucket: {S3_BUCKET}")
        s3_client.upload_fileobj(
            pdf_buffer,
            S3_BUCKET,
            pdf_filename,
            ExtraArgs={'ContentType': 'application/pdf'}
        )
        
        # Generate presigned download URL
        pdf_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': pdf_filename},
            ExpiresIn=3600
        )
        print("PDF compilation and S3 upload successful.")
        
    except Exception as e:
        update_status(task_id, f"FAILED (PDF compilation error: {str(e)})")
        raise e

    # Save outputs to the state payload
    event['pdf_filename'] = pdf_filename
    event['pdf_url'] = pdf_url
    return event
