import os
import boto3

transcribe_client = boto3.client("transcribe")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

def transcribe(job_id: str, file_key: str) -> str:
    job_uri = f"s3://{S3_BUCKET_NAME}/telegram-files/{file_key}"

    transcribe_client.start_transcription_job(
        TranscriptionJobName=job_id,
        Media={"MediaFileUri": job_uri},
        MediaFormat="ogg",
        IdentifyLanguage=True,
        OutputBucketName=S3_BUCKET_NAME,
        OutputKey=f"transcripts/{job_id}.json"
    )

    return job_id