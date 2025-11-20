"""
Pydantic schemas for Media Service
"""
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime


class MediaUploadResponse(BaseModel):
    """Media upload response"""
    id: int
    filename: str
    file_path: str
    file_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: str
    status: str
    thumbnail_url: Optional[str] = None
    urls: Dict[str, str] = {}
    created_at: datetime


class MediaDetail(BaseModel):
    """Media detail response"""
    id: int
    user_id: int
    type_id: int
    post_id: Optional[int] = None
    original_filename: str
    stored_filename: str
    file_path: str
    file_size: int
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    aspect_ratio: Optional[float] = None
    thumbnail_path: Optional[str] = None
    thumbnail_width: Optional[int] = None
    thumbnail_height: Optional[int] = None
    processed_versions: Optional[Dict] = None
    status: str
    upload_progress: int
    exif_data: Optional[Dict] = None
    created_at: datetime
    updated_at: datetime


class MediaListResponse(BaseModel):
    """Media list response"""
    items: list[MediaDetail]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    success: bool = False
