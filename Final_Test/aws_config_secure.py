# Secure AWS Configuration
import os
import boto3

def get_s3_client():
    """Get S3 client with credentials from environment"""
    aws_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    if not aws_key or not aws_secret:
        raise ValueError("AWS credentials not found in environment")
    
    return boto3.client('s3',
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret,
        region_name=region)

def upload_to_s3(file_path: str, bucket: str, key: str):
    client = get_s3_client()
    client.upload_file(file_path, bucket, key)
