"""
Instagram Clone - Media Service
Main FastAPI application for media upload and processing
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from io import BytesIO
import os

from config import settings
from database import db, get_db, Database
from storage import storage
from image_processor import ImageProcessor
from auth import get_current_user, get_current_user_optional
from schemas import (
    MediaUploadResponse, MediaDetail, MediaListResponse,
    MessageResponse, ErrorResponse
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 Starting Media Service...")
    await db.connect()
    print(f"✓ Media Service started on {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"✓ Storage type: {settings.STORAGE_TYPE}")
    print(f"✓ Bucket name: {settings.S3_BUCKET_NAME}")

    yield

    # Shutdown
    print("👋 Shutting down Media Service...")
    await db.disconnect()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Media service for Instagram clone with image/video processing",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


def validate_file_size(file: UploadFile) -> bool:
    """Validate file size"""
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    return file_size <= max_size


def get_file_extension(filename: str) -> str:
    """Get file extension"""
    return f".{filename.rsplit('.', 1)[-1].lower()}" if '.' in filename else ""


def is_image(filename: str) -> bool:
    """Check if file is an image"""
    ext = get_file_extension(filename)
    return ext in settings.ALLOWED_IMAGE_EXTENSIONS


def is_video(filename: str) -> bool:
    """Check if file is a video"""
    ext = get_file_extension(filename)
    return ext in settings.ALLOWED_VIDEO_EXTENSIONS


@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "storage_type": settings.STORAGE_TYPE,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/media/upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED, tags=["Media"])
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Upload media file (image or video)

    - **file**: Media file to upload
    - Supports images: jpg, jpeg, png, gif, webp
    - Supports videos: mp4, mov, avi, mkv
    - Max file size: 100MB
    - Requires authentication
    """
    # Validate file type
    if not (is_image(file.filename) or is_video(file.filename)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {settings.ALLOWED_IMAGE_EXTENSIONS + settings.ALLOWED_VIDEO_EXTENSIONS}"
        )

    # Validate file size
    if not validate_file_size(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
        )

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Determine media type
    if is_image(file.filename):
        media_type_id = 1  # image
        mime_type = f"image/{get_file_extension(file.filename)[1:]}"
    else:
        media_type_id = 2  # video
        mime_type = f"video/{get_file_extension(file.filename)[1:]}"

    # Generate unique filename
    stored_filename = ImageProcessor.generate_unique_filename(file.filename, current_user["id"])

    # Process image if it's an image file
    width = None
    height = None
    aspect_ratio = None
    thumbnail_path = None
    processed_versions = {}

    if is_image(file.filename):
        try:
            # Get image dimensions
            width, height = ImageProcessor.get_image_dimensions(file_content)
            aspect_ratio = width / height if height > 0 else None

            # Process image into multiple sizes
            processed_images = ImageProcessor.process_upload(
                file_content,
                settings.IMAGE_SIZES,
                settings.IMAGE_QUALITY
            )

            # Upload original
            original_buffer = BytesIO(file_content)
            storage.upload_file(
                original_buffer,
                stored_filename,
                mime_type,
                metadata={
                    "user_id": str(current_user["id"]),
                    "original_filename": file.filename
                }
            )

            # Upload processed versions
            for size_name, image_buffer in processed_images.items():
                if size_name == 'original':
                    continue

                size_filename = stored_filename.replace(
                    get_file_extension(stored_filename),
                    f"_{size_name}{get_file_extension(stored_filename)}"
                )

                storage.upload_file(
                    image_buffer,
                    size_filename,
                    "image/jpeg"
                )

                processed_versions[size_name] = size_filename

            # Create thumbnail
            thumbnail_filename = stored_filename.replace(
                get_file_extension(stored_filename),
                f"_thumb{get_file_extension(stored_filename)}"
            )

            from PIL import Image
            with Image.open(BytesIO(file_content)) as img:
                thumbnail_buffer = ImageProcessor.create_thumbnail(
                    img,
                    settings.IMAGE_SIZES.get("thumbnail", (150, 150)),
                    settings.THUMBNAIL_QUALITY
                )

            storage.upload_file(
                thumbnail_buffer,
                thumbnail_filename,
                "image/jpeg"
            )

            thumbnail_path = thumbnail_filename

        except Exception as e:
            print(f"Error processing image: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process image: {str(e)}"
            )
    else:
        # For videos, just upload the original
        video_buffer = BytesIO(file_content)
        storage.upload_file(
            video_buffer,
            stored_filename,
            mime_type,
            metadata={
                "user_id": str(current_user["id"]),
                "original_filename": file.filename
            }
        )

    # Save metadata to database
    try:
        import json
        media_record = await database.fetch_one(
            """
            INSERT INTO media_files (
                user_id, type_id, original_filename, stored_filename,
                file_path, file_size, mime_type, width, height,
                aspect_ratio, thumbnail_path, processed_versions, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id, user_id, original_filename, stored_filename, file_path,
                      file_size, mime_type, width, height, status, created_at
            """,
            current_user["id"],
            media_type_id,
            file.filename,
            stored_filename,
            stored_filename,
            file_size,
            mime_type,
            width,
            height,
            aspect_ratio,
            thumbnail_path,
            json.dumps(processed_versions) if processed_versions else None,
            "completed"
        )
    except Exception as e:
        print(f"Database error: {e}")
        # Clean up uploaded files
        storage.delete_file(stored_filename)
        if thumbnail_path:
            storage.delete_file(thumbnail_path)
        for size_file in processed_versions.values():
            storage.delete_file(size_file)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save media metadata: {str(e)}"
        )

    # Generate URLs
    urls = {}
    if is_image(file.filename):
        for size_name, size_filename in processed_versions.items():
            urls[size_name] = f"/api/v1/media/{media_record['id']}/file?size={size_name}"

    thumbnail_url = f"/api/v1/media/{media_record['id']}/thumbnail" if thumbnail_path else None

    return MediaUploadResponse(
        id=media_record["id"],
        filename=media_record["original_filename"],
        file_path=media_record["file_path"],
        file_size=media_record["file_size"],
        width=media_record["width"],
        height=media_record["height"],
        mime_type=media_record["mime_type"],
        status=media_record["status"],
        thumbnail_url=thumbnail_url,
        urls=urls,
        created_at=media_record["created_at"]
    )


@app.get("/api/v1/media/{media_id}", response_model=MediaDetail, tags=["Media"])
async def get_media(
    media_id: int,
    database: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional)
):
    """
    Get media metadata by ID

    - **media_id**: Media file ID
    - Authentication optional
    """
    media = await database.fetch_one(
        """
        SELECT * FROM media_files WHERE id = $1
        """,
        media_id
    )

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    return MediaDetail(**dict(media))


@app.get("/api/v1/media/{media_id}/file", tags=["Media"])
async def download_media(
    media_id: int,
    size: Optional[str] = Query(None, description="Image size: thumbnail, small, medium, large, or original"),
    database: Database = Depends(get_db)
):
    """
    Download media file

    - **media_id**: Media file ID
    - **size**: For images, specify size (thumbnail, small, medium, large, original)
    """
    media = await database.fetch_one(
        """
        SELECT * FROM media_files WHERE id = $1
        """,
        media_id
    )

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    # Determine which file to download
    file_path = media["file_path"]

    if size and media["type_id"] == 1:  # Image
        import json
        processed_versions = json.loads(media.get("processed_versions") or '{}')
        if size in processed_versions:
            file_path = processed_versions[size]
        elif size != "original":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Size '{size}' not available for this image"
            )

    # Download from storage
    file_data = storage.download_file(file_path)

    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found in storage"
        )

    return StreamingResponse(
        BytesIO(file_data),
        media_type=media["mime_type"],
        headers={
            "Content-Disposition": f'inline; filename="{media["original_filename"]}"'
        }
    )


@app.get("/api/v1/media/{media_id}/thumbnail", tags=["Media"])
async def get_thumbnail(
    media_id: int,
    database: Database = Depends(get_db)
):
    """
    Get media thumbnail

    - **media_id**: Media file ID
    """
    media = await database.fetch_one(
        """
        SELECT thumbnail_path, original_filename FROM media_files WHERE id = $1
        """,
        media_id
    )

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    if not media["thumbnail_path"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available for this media"
        )

    # Download thumbnail
    thumbnail_data = storage.download_file(media["thumbnail_path"])

    if not thumbnail_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail file not found in storage"
        )

    return StreamingResponse(
        BytesIO(thumbnail_data),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="thumb_{media["original_filename"]}"'
        }
    )


@app.get("/api/v1/media/user/{user_id}", response_model=MediaListResponse, tags=["Media"])
async def get_user_media(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    database: Database = Depends(get_db)
):
    """
    Get all media for a specific user

    - **user_id**: User ID
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    """
    offset = (page - 1) * page_size

    # Get total count
    total = await database.fetch_one(
        "SELECT COUNT(*) as count FROM media_files WHERE user_id = $1",
        user_id
    )

    # Get media items
    media_items = await database.fetch_all(
        """
        SELECT * FROM media_files
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        page_size,
        offset
    )

    items = [MediaDetail(**dict(item)) for item in media_items]

    return MediaListResponse(
        items=items,
        total=total["count"],
        page=page,
        page_size=page_size
    )


@app.delete("/api/v1/media/{media_id}", response_model=MessageResponse, tags=["Media"])
async def delete_media(
    media_id: int,
    current_user: dict = Depends(get_current_user),
    database: Database = Depends(get_db)
):
    """
    Delete media file

    - **media_id**: Media file ID
    - Requires authentication
    - Only the owner can delete their media
    """
    # Check if media exists and belongs to user
    media = await database.fetch_one(
        """
        SELECT * FROM media_files WHERE id = $1
        """,
        media_id
    )

    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found"
        )

    if media["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this media"
        )

    # Delete from storage
    storage.delete_file(media["file_path"])

    # Delete thumbnail
    if media["thumbnail_path"]:
        storage.delete_file(media["thumbnail_path"])

    # Delete processed versions
    if media["processed_versions"]:
        import json
        processed_versions = json.loads(media["processed_versions"])
        for size_file in processed_versions.values():
            storage.delete_file(size_file)

    # Delete from database
    await database.execute(
        "DELETE FROM media_files WHERE id = $1",
        media_id
    )

    return MessageResponse(message="Media deleted successfully")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
