import os
import json
import uuid
from datetime import datetime
import boto3
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
region_name = os.getenv('AWS_REGION', 'us-east-1')
sfn_client = boto3.client('stepfunctions', region_name=region_name)
dynamodb = boto3.resource('dynamodb', region_name=region_name)
papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))
STATE_MACHINE_ARN = os.getenv('STATE_MACHINE_ARN')

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

def handler(event, context):
    """
    AWS Lambda entry point for starting a question generation task.
    Triggered by: POST /api/generate-questions
    """
    if event.get('httpMethod') == 'OPTIONS':
        return make_response(200, {"message": "CORS preflight successful"})
        
    try:
        body_str = event.get('body', '')
        if not body_str:
            return make_response(400, {'success': False, 'error': 'Empty request body'})
            
        data = json.loads(body_str)
    except Exception as e:
        return make_response(400, {'success': False, 'error': f'Invalid JSON body: {str(e)}'})

    # Validate required parameters
    required_fields = ['email', 'subjectName', 'classGrade', 'topics']
    for field in required_fields:
        if field not in data:
            return make_response(400, {'success': False, 'error': f"Missing required field: {field}"})

    task_id = str(uuid.uuid4())
    created_at = datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

    # Initial state to be stored in DynamoDB
    paper_data = {
        'paper_id': task_id,
        'email': data['email'],
        'subjectName': data['subjectName'],
        'classGrade': data['classGrade'],
        'topics': data['topics'],
        'status': 'PENDING',
        'created_at': created_at,
        'attempts_used': 0
    }

    # Save initial pending status to DynamoDB
    try:
        papers_table.put_item(Item=paper_data)
    except Exception as e:
        return make_response(500, {'success': False, 'error': f"Failed to initialize database record: {str(e)}"})

    # Trigger Step Function Execution
    if not STATE_MACHINE_ARN:
        return make_response(500, {'success': False, 'error': 'STATE_MACHINE_ARN environment variable is not configured'})

    try:
        sfn_client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=task_id,
            input=json.dumps({
                'task_id': task_id,
                'email': data['email'],
                'subjectName': data['subjectName'],
                'classGrade': data['classGrade'],
                'topics': data['topics'],
                'previous_paper_id': data.get('previous_paper_id'),
                'attempts_used': 0
            })
        )
    except Exception as e:
        # If Step Function fail to start, update status to FAILED in DB
        try:
            papers_table.update_item(
                Key={'paper_id': task_id},
                UpdateExpression="SET #s = :status, #err = :err",
                ExpressionAttributeNames={'#s': 'status', '#err': 'error'},
                ExpressionAttributeValues={':status': 'FAILED', ':err': f"Failed to initiate workflow: {str(e)}"}
            )
        except Exception:
            pass
        return make_response(500, {'success': False, 'error': f"Failed to start Step Function execution: {str(e)}"})

    return make_response(202, {
        'success': True,
        'task_id': task_id,
        'status': 'PENDING'
    })
