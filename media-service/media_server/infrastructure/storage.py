"""
Storage management for S3/MinIO
"""
import boto3
from botocore.exceptions import ClientError
from typing import BinaryIO, Optional
from config import settings
import logging

logger = logging.getLogger(__name__)


class StorageManager:
    """Manage file storage in S3/MinIO"""

    def __init__(self):
        """Initialize storage client"""
        if settings.STORAGE_TYPE == "minio":
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or "minioadmin",
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or "minioadmin",
                region_name=settings.AWS_REGION
            )
        else:
            self.client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )

        self.bucket_name = settings.S3_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} exists")
        except ClientError:
            try:
                if settings.AWS_REGION == "us-east-1":
                    self.client.create_bucket(Bucket=self.bucket_name)
                else:
                    self.client.create_bucket(
                        Bucket=self.bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
                    )
                logger.info(f"Created bucket {self.bucket_name}")
            except ClientError as e:
                logger.error(f"Failed to create bucket: {e}")

    def upload_file(
        self,
        file_data: BinaryIO,
        key: str,
        content_type: str = "image/jpeg",
        metadata: Optional[dict] = None
    ) -> bool:
        """
        Upload file to storage

        Args:
            file_data: File-like object
            key: Object key (path) in storage
            content_type: MIME type
            metadata: Optional metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            extra_args = {
                'ContentType': content_type,
            }

            if metadata:
                extra_args['Metadata'] = metadata

            file_data.seek(0)
            self.client.upload_fileobj(
                file_data,
                self.bucket_name,
                key,
                ExtraArgs=extra_args
            )

            logger.info(f"Uploaded {key} to {self.bucket_name}")
            return True

        except ClientError as e:
            logger.error(f"Failed to upload {key}: {e}")
            return False

    def download_file(self, key: str) -> Optional[bytes]:
        """
        Download file from storage

        Args:
            key: Object key (path) in storage

        Returns:
            File bytes or None if not found
        """
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read()
        except ClientError as e:
            logger.error(f"Failed to download {key}: {e}")
            return None

    def delete_file(self, key: str) -> bool:
        """
        Delete file from storage

        Args:
            key: Object key (path) in storage

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted {key} from {self.bucket_name}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for temporary access

        Args:
            key: Object key (path) in storage
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL or None if failed
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {key}: {e}")
            return None

    def file_exists(self, key: str) -> bool:
        """
        Check if file exists in storage

        Args:
            key: Object key (path) in storage

        Returns:
            True if exists, False otherwise
        """
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False


# Global storage instance
storage = StorageManager()
