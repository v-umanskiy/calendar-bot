import os
import asyncio
import mimetypes
import boto3

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3_client = boto3.client("s3")

async def upload_file_to_s3(file_bytes: bytes, file_id: str) -> tuple[str, str]:
    mime_type, _ = mimetypes.guess_type(file_id)
    if not mime_type:
        mime_type = "application/octet-stream"

    try:
        key = f"telegram-files/{file_id}"
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=mime_type,
        )
        return f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{key}", key
    except Exception as e:
        print(f"S3 upload error: {repr(e)}")
        return None

async def download_file_from_s3(key: str) -> bytes | None:
    if not S3_BUCKET_NAME:
        print("S3_BUCKET_NAME not set. Cannot download file.")
        return None

    try:
        def _download():
            response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_download)
    except Exception as e:
        print(f"S3 download error: {repr(e)}")
        return None


async def delete_files_from_s3(keys: list[str]) -> None:
    if not keys:
        return

    if not S3_BUCKET_NAME:
        print("S3_BUCKET_NAME not set. Cannot delete files.")
        return

    async def _delete_batch(batch: list[str]):
        objects = [{"Key": key} for key in batch]
        await asyncio.to_thread(
            s3_client.delete_objects,
            Bucket=S3_BUCKET_NAME,
            Delete={"Objects": objects, "Quiet": True},
        )

    try:
        for start in range(0, len(keys), 1000):
            batch = keys[start:start + 1000]
            if batch:
                await _delete_batch(batch)
    except Exception as e:
        print(f"S3 delete error: {repr(e)}")
