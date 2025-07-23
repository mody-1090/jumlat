import boto3
import os
from werkzeug.utils import secure_filename

AWS_ACCESS_KEY   = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_KEY   = os.environ['AWS_SECRET_ACCESS_KEY']
AWS_BUCKET_NAME  = os.environ['AWS_S3_BUCKET_NAME']
AWS_REGION       = os.environ.get('AWS_S3_REGION', 'us-east-1')

s3 = boto3.client(
    "s3",
    aws_access_key_id     = AWS_ACCESS_KEY,
    aws_secret_access_key = AWS_SECRET_KEY,
    region_name           = AWS_REGION,
)

def upload_file_to_s3(file, folder="uploads"):
    if hasattr(file, "filename") and file.filename:
        filename = secure_filename(file.filename)
    else:
        filename = os.path.basename(getattr(file, "name", "file"))

    s3_path = f"{folder}/{filename}"

    try:
        # نرفع بدون تحديد أي ACL
        s3.upload_fileobj(
            file,
            AWS_BUCKET_NAME,
            s3_path
        )
        return f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_path}"
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None
