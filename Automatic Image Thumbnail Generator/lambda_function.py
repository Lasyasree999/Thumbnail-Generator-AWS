import boto3
import os
import json
from PIL import Image
import io

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    for record in event['Records']:
        # Parse SQS Message
        body = json.loads(record['body'].replace("'", '"'))
        bucket = body['bucket']
        key = f"uploads/{body['filename']}"
        thumbnail_key = f"thumbnails/{body['filename']}"
        
        # Download Image
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_content = response['Body'].read()
        
        # Process Thumbnail
        with Image.open(io.BytesIO(image_content)) as img:
            img.thumbnail((200, 200))
            buffer = io.BytesIO()
            img.save(buffer, format=img.format)
            buffer.seek(0)
            
            # Upload Thumbnail
            s3_client.put_object(
                Bucket=bucket,
                Key=thumbnail_key,
                Body=buffer,
                ContentType=response['ContentType']
            )
            
    return {
        'statusCode': 200,
        'body': json.dumps('Thumbnail generated successfully!')
    }