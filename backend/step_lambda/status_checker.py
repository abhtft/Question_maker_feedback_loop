import os
import json
import boto3
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
region_name = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=region_name)
papers_table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_PAPERS', 'question_papers'))

def convert_decimals_to_floats(obj):
    """Recursively convert DynamoDB Decimal types back to float/int for JSON serialization."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals_to_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_floats(x) for x in obj]
    return obj

def make_response(status_code, body_dict):
    """Generate a standard API Gateway proxy response with CORS headers."""
    # Convert Decimals back to floats/ints before JSON encoding
    serializable_body = convert_decimals_to_floats(body_dict)
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
        },
        "body": json.dumps(serializable_body)
    }

def handler(event, context):
    """
    AWS Lambda entry point.
    Triggered by: GET /api/status/{task_id}
    """
    if event.get('httpMethod') == 'OPTIONS':
        return make_response(200, {"message": "CORS preflight successful"})
        
    # Resolve path parameters (v1 and v2 compatible)
    path_parameters = event.get('pathParameters') or {}
    task_id = path_parameters.get('task_id')
    
    # Fallback to query string or event body if path parameters are empty
    if not task_id:
        query_params = event.get('queryStringParameters') or {}
        task_id = query_params.get('task_id')

    if not task_id:
        return make_response(400, {'success': False, 'error': 'Missing task_id parameter'})

    try:
        response = papers_table.get_item(Key={'paper_id': task_id})
    except Exception as e:
        return make_response(500, {'success': False, 'error': f"Failed to retrieve database record: {str(e)}"})

    if 'Item' not in response:
        return make_response(404, {'success': False, 'error': f"Task not found: {task_id}"})

    item = response['Item']
    
    # Return current state of task
    return make_response(200, {
        'success': True,
        'task_id': task_id,
        'status': item.get('status'),
        'attempts_used': item.get('attempts_used', 1),
        'created_at': item.get('created_at'),
        'pdf_url': item.get('pdf_url'),
        'google_form_url': item.get('google_form_url'),
        'questions': item.get('questions'),
        'error': item.get('error')
    })
