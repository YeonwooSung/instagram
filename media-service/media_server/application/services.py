"""
Application services - Business logic layer
"""
from typing import BinaryIO, Optional, Tuple
from fastapi import HTTPException, status, UploadFile
from PIL import Image
from io import BytesIO

from domain.models import Media, MediaType, MediaUploadResult
from domain.repositories import IMediaRepository
from infrastructure.storage import StorageManager
from infrastructure.image_processor import ImageProcessor
from config import settings


class MediaService:
    """Media service - handles media-related business logic"""

    def __init__(
        self,
        media_repository: IMediaRepository,
        storage_manager: StorageManager
    ):
        self.media_repo = media_repository
        self.storage = storage_manager
        self.image_processor = ImageProcessor()

    async def upload_media(
        self,
        file: UploadFile,
        user_id: int,
        post_id: Optional[int] = None
    ) -> MediaUploadResult:
        """
        Upload media file

        Args:
            file: Uploaded file
            user_id: User ID
            post_id: Optional post ID

        Returns:
            MediaUploadResult with media details
        """
        # Validate file
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only image files are supported"
            )

        # Read file data
        file_data = await file.read()
        file_size = len(file_data)

        # Validate file size
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE} bytes"
            )

        # Process image
        try:
            with Image.open(BytesIO(file_data)) as img:
                width, height = img.size

                # Generate unique filename
                original_filename = self.image_processor.generate_unique_filename(
                    file.filename,
                    user_id
                )

                # Resize and save original
                original_buffer = BytesIO()
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                img.save(original_buffer, format='JPEG', quality=90, optimize=True)
                original_buffer.seek(0)

                # Upload original
                success = self.storage.upload_file(
                    original_buffer,
                    original_filename,
                    content_type='image/jpeg'
                )

                if not success:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to upload file to storage"
                    )

                # Create thumbnail
                thumbnail_buffer = self.image_processor.create_thumbnail(img.copy())
                thumbnail_filename = original_filename.replace('.', '_thumb.')

                self.storage.upload_file(
                    thumbnail_buffer,
                    thumbnail_filename,
                    content_type='image/jpeg'
                )

        except Exception as e:
            # Clean up uploaded files on error
            try:
                self.storage.delete_file(original_filename)
                self.storage.delete_file(thumbnail_filename)
            except:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process image: {str(e)}"
            )

        # Save to database
        media = await self.media_repo.create(
            user_id=user_id,
            post_id=post_id,
            media_type=MediaType.IMAGE,
            file_path=original_filename,
            thumbnail_path=thumbnail_filename,
            width=width,
            height=height,
            file_size=file_size,
            mime_type=file.content_type
        )

        # Return result
        return MediaUploadResult(
            media_id=media.id,
            media_url=media.get_url(settings.MEDIA_BASE_URL),
            thumbnail_url=media.get_thumbnail_url(settings.MEDIA_BASE_URL),
            width=width,
            height=height,
            file_size=file_size
        )

    async def get_media(self, media_id: int) -> Media:
        """Get media by ID"""
        media = await self.media_repo.find_by_id(media_id)
        if not media:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found"
            )
        return media

    async def delete_media(self, media_id: int, user_id: int) -> None:
        """Delete media"""
        media = await self.get_media(media_id)

        if not media.is_owner(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this media"
            )

        # Delete from storage
        self.storage.delete_file(media.file_path)
        if media.thumbnail_path:
            self.storage.delete_file(media.thumbnail_path)

        # Delete from database
        await self.media_repo.delete(media_id)
