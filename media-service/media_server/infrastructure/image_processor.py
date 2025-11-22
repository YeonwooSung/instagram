"""
Image processing utilities for resizing, thumbnails, and format conversion
"""
from PIL import Image, ExifTags
from io import BytesIO
from typing import Tuple, Dict, Optional
import hashlib
from datetime import datetime


class ImageProcessor:
    """Image processing and manipulation"""

    @staticmethod
    def generate_unique_filename(original_filename: str, user_id: int) -> str:
        """Generate a unique filename for storage"""
        timestamp = datetime.utcnow().isoformat()
        hash_input = f"{user_id}_{original_filename}_{timestamp}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        # Get file extension
        ext = original_filename.rsplit('.', 1)[-1].lower()
        return f"{user_id}/{file_hash}.{ext}"

    @staticmethod
    def fix_image_orientation(image: Image.Image) -> Image.Image:
        """Fix image orientation based on EXIF data"""
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break

            exif = dict(image._getexif().items())

            if exif[orientation] == 3:
                image = image.rotate(180, expand=True)
            elif exif[orientation] == 6:
                image = image.rotate(270, expand=True)
            elif exif[orientation] == 8:
                image = image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            # No EXIF data or orientation tag
            pass

        return image

    @staticmethod
    def resize_image(image: Image.Image, target_size: Tuple[int, int], quality: int = 90) -> BytesIO:
        """
        Resize image maintaining aspect ratio

        Args:
            image: PIL Image object
            target_size: Target size (width, height)
            quality: JPEG quality (1-100)

        Returns:
            BytesIO buffer containing resized image
        """
        # Fix orientation
        image = ImageProcessor.fix_image_orientation(image)

        # Convert RGBA to RGB if necessary
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        # Calculate aspect ratio
        img_width, img_height = image.size
        target_width, target_height = target_size

        # Maintain aspect ratio
        img_ratio = img_width / img_height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # Image is wider
            new_height = target_height
            new_width = int(target_height * img_ratio)
        else:
            # Image is taller or same ratio
            new_width = target_width
            new_height = int(target_width / img_ratio)

        # Resize image
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Crop to exact target size (center crop)
        left = (new_width - target_width) / 2
        top = (new_height - target_height) / 2
        right = left + target_width
        bottom = top + target_height

        image = image.crop((left, top, right, bottom))

        # Save to buffer
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)

        return buffer

    @staticmethod
    def create_thumbnail(image: Image.Image, size: Tuple[int, int] = (150, 150), quality: int = 85) -> BytesIO:
        """
        Create thumbnail for image

        Args:
            image: PIL Image object
            size: Thumbnail size (width, height)
            quality: JPEG quality (1-100)

        Returns:
            BytesIO buffer containing thumbnail
        """
        return ImageProcessor.resize_image(image, size, quality)

    @staticmethod
    def extract_exif_data(image: Image.Image) -> Dict:
        """
        Extract EXIF metadata from image

        Args:
            image: PIL Image object

        Returns:
            Dictionary of EXIF data
        """
        exif_data = {}

        try:
            exif = image._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    exif_data[tag] = str(value)
        except (AttributeError, KeyError, IndexError):
            pass

        return exif_data

    @staticmethod
    def get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
        """
        Get image dimensions without fully loading it

        Args:
            image_bytes: Image bytes

        Returns:
            Tuple of (width, height)
        """
        with Image.open(BytesIO(image_bytes)) as img:
            return img.size

    @staticmethod
    def process_upload(
        image_bytes: bytes,
        sizes: Dict[str, Tuple[int, int]],
        quality: int = 90
    ) -> Dict[str, BytesIO]:
        """
        Process uploaded image into multiple sizes

        Args:
            image_bytes: Original image bytes
            sizes: Dictionary of size names to dimensions
            quality: JPEG quality

        Returns:
            Dictionary of size names to processed image buffers
        """
        with Image.open(BytesIO(image_bytes)) as img:
            processed_images = {}

            # Create original size
            original_buffer = BytesIO(image_bytes)
            processed_images['original'] = original_buffer

            # Create other sizes
            for size_name, dimensions in sizes.items():
                processed_images[size_name] = ImageProcessor.resize_image(
                    img.copy(),
                    dimensions,
                    quality
                )

            return processed_images
