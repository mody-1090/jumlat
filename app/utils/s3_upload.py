import boto3
import os
from werkzeug.utils import secure_filename

AWS_ACCESS_KEY   = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY   = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_BUCKET_NAME  = os.environ.get('AWS_S3_BUCKET_NAME')
AWS_REGION       = os.environ.get('AWS_S3_REGION', 'auto')  # R2 الأفضل auto
S3_ENDPOINT_URL  = os.environ.get('S3_ENDPOINT_URL')        # <-- جديد
PUBLIC_BASE_URL  = os.environ.get('PUBLIC_FILES_BASE_URL')  # <-- جديد

s3 = boto3.client(
    "s3",
    aws_access_key_id     = AWS_ACCESS_KEY,
    aws_secret_access_key = AWS_SECRET_KEY,
    region_name           = AWS_REGION,
    endpoint_url          = S3_ENDPOINT_URL,   # <-- هذا أهم سطر لـ R2
)

def upload_file_to_s3(file, folder="uploads"):
    if hasattr(file, "filename") and file.filename:
        filename = secure_filename(file.filename)
    else:
        filename = os.path.basename(getattr(file, "name", "file"))

    s3_path = f"{folder}/{filename}"

    try:
        s3.upload_fileobj(file, AWS_BUCKET_NAME, s3_path)

        # نرجّع رابط عام من r2.dev (اللي أعطيتني)
        public_base = (PUBLIC_BASE_URL or "").rstrip("/")
        if public_base:
            return f"{public_base}/{s3_path}"

        # احتياط: لو ما حطيت PUBLIC_FILES_BASE_URL
        return s3_path

    except Exception as e:
        print(f"Error uploading to R2: {e}")
        return None
