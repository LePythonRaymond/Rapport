import os
import requests
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageOps
from io import BytesIO
from datetime import datetime
import config

class ImageHandler:
    """
    Handles downloading images from Google Chat and uploading them to Notion.
    """

    def __init__(self, google_auth_service=None, notion_client=None):
        """
        Initialize the image handler.

        Args:
            google_auth_service: Authenticated Google service for downloading
            notion_client: Notion client for uploading
        """
        self.google_service = google_auth_service
        self.notion_client = notion_client

    def download_image_from_chat(self, attachment_info: Dict[str, Any], space_id: str) -> Optional[bytes]:
        """
        Download an image from Google Chat attachment.

        Args:
            attachment_info: Attachment information from Google Chat API
            space_id: Google Chat space ID

        Returns:
            Image content as bytes or None if download fails
        """
        try:
            if not self.google_service:
                print("Google service not available for image download")
                return None

            # Get the attachment resource name from attachmentDataRef
            attachment_data_ref = attachment_info.get('attachmentDataRef', {})
            resource_name = attachment_data_ref.get('resourceName', '')

            if not resource_name:
                print("No resource name found for attachment")
                return None

            print(f"Downloading attachment with resource name: {resource_name}")

            # Use the Google Chat API media endpoint to download the attachment
            # The resource name should be the full attachment resource name
            request = self.google_service.media().download_media(
                resourceName=resource_name,
                alt='media'  # This is required for binary content
            )

            # Execute the request
            content = request.execute()

            if content:
                print(f"Successfully downloaded image: {attachment_info.get('name', 'unknown')}")
                return content
            else:
                print("Downloaded content is empty")
                return None

        except Exception as e:
            print(f"Error downloading image {attachment_info.get('name', 'unknown')}: {e}")
            return None

    def download_image_from_url(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[bytes]:
        """
        Download an image from a URL.

        Args:
            url: Image URL
            headers: Optional headers for the request

        Returns:
            Image content as bytes or None if download fails
        """
        try:
            response = requests.get(url, headers=headers or {}, timeout=30)
            response.raise_for_status()

            if response.content:
                print(f"Successfully downloaded image from URL")
                return response.content
            else:
                print("Downloaded content is empty")
                return None

        except Exception as e:
            print(f"Error downloading image from URL: {e}")
            return None

    def validate_image(self, image_bytes: bytes) -> Tuple[bool, str]:
        """
        Validate that the downloaded content is a valid image.
        Note: Size check removed - File Upload API has no size limits.
        Images are resized to 600x800 @ 70% quality (~50KB) before upload.

        Args:
            image_bytes: Image content as bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Try to open with PIL
            image = Image.open(BytesIO(image_bytes))
            image.verify()  # Verify the image

            # No size check needed - File Upload API handles any size
            # Images are resized to 600x800 @ 70% quality before upload anyway
            return True, ""

        except Exception as e:
            return False, f"Invalid image: {e}"

    def resize_image_if_needed(self, image_bytes: bytes, max_width: int = 600, max_height: int = 800) -> bytes:
        """
        Resize image if it's too large while maintaining aspect ratio.
        Optimized for Notion uploads with smaller size and lower quality.

        Args:
            image_bytes: Original image bytes
            max_width: Maximum width (default 600 for Notion uploads)
            max_height: Maximum height (default 800 for Notion uploads)

        Returns:
            Resized and optimized image bytes
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            # Apply EXIF orientation correction (handles rotation/flip based on EXIF metadata)
            image = ImageOps.exif_transpose(image)
            original_width, original_height = image.size

            # Always resize for consistency and optimization
            # Calculate new dimensions maintaining aspect ratio
            ratio = min(max_width / original_width, max_height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)

            # Resize the image
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to RGB if needed (for JPEG compatibility)
            if resized_image.mode in ('RGBA', 'P'):
                rgb_image = Image.new('RGB', resized_image.size, (255, 255, 255))
                if resized_image.mode == 'P':
                    resized_image = resized_image.convert('RGBA')
                rgb_image.paste(resized_image, mask=resized_image.split()[-1] if resized_image.mode == 'RGBA' else None)
                resized_image = rgb_image

            # Convert back to bytes with optimized quality
            output = BytesIO()
            resized_image.save(output, format='JPEG', quality=70, optimize=True)
            resized_bytes = output.getvalue()

            print(f"Optimized image from {original_width}x{original_height} ({len(image_bytes)} bytes) to {new_width}x{new_height} ({len(resized_bytes)} bytes)")
            return resized_bytes

        except Exception as e:
            print(f"Error resizing image: {e}")
            return image_bytes  # Return original if resize fails

    def upload_image_to_notion(self, image_bytes: bytes, filename: str = None) -> Optional[str]:
        """
        Upload image to Notion using the File Upload API and return the Notion-hosted URL.
        Uses 3-step process: create upload, send file, complete upload.

        Args:
            image_bytes: Image content as bytes
            filename: Optional filename for the image

        Returns:
            Notion-hosted image URL or None if upload fails
        """
        try:
            if not self.notion_client:
                print("Notion client not available for image upload")
                return None

            # Resize and optimize the image first (this handles large images)
            image_bytes = self.resize_image_if_needed(image_bytes)

            # Validate the resized image format (after resizing, size is no longer an issue)
            is_valid, error_msg = self.validate_image(image_bytes)
            if not is_valid:
                print(f"Image validation failed: {error_msg}")
                return None

            # Generate filename if not provided
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"intervention_image_{timestamp}.jpg"

            # Ensure filename ends with .jpg
            if not filename.lower().endswith(('.jpg', '.jpeg')):
                filename = f"{filename}.jpg"

            file_size = len(image_bytes)
            print(f"📤 Uploading {filename} ({file_size} bytes) to Notion...")

            # Step 1: Create file upload
            upload_info = self.notion_client.create_file_upload(filename, file_size)
            if not upload_info:
                print("Failed to create file upload")
                return None

            # The response structure might vary, let's handle both cases
            upload_url = upload_info.get('upload_url')
            file_upload_id = upload_info.get('id') or upload_info.get('file_upload_id')

            if not upload_url or not file_upload_id:
                print(f"Missing upload URL or file upload ID. Got: {upload_info}")
                return None

            # Step 2: Send file to upload URL
            if not self.notion_client.send_file_to_upload(upload_url, image_bytes, "image/jpeg"):
                print("Failed to send file to upload URL")
                return None

            # NOTE: We don't call /complete - that's called automatically when the file is attached to a page
            # Instead, we return a special format that indicates this is a file_upload reference
            # The format is: notion://file_upload/{file_upload_id}
            notion_reference = f"notion://file_upload/{file_upload_id}"

            print(f"✅ Image uploaded to Notion: {filename} (file_upload_id: {file_upload_id[:8]}...)")
            return notion_reference

        except Exception as e:
            print(f"❌ Error uploading image to Notion: {e}")
            import traceback
            traceback.print_exc()
            return None

    def process_intervention_images(self, intervention: Dict[str, Any], space_id: str) -> List[str]:
        """
        Process all images for an intervention and categorize them.

        Args:
            intervention: Intervention dictionary with images (all, regular, avant, apres)
            space_id: Google Chat space ID

        Returns:
            List of Notion image URLs (in original order)
        """
        notion_image_urls = []

        # Create mappings for categorized images
        notion_regular_images = []
        notion_avant_images = []
        notion_apres_images = []

        # Get categorized image lists
        regular_images = intervention.get('regular_images', [])
        avant_images = intervention.get('avant_images', [])
        apres_images = intervention.get('apres_images', [])

        # Create a lookup by image name for categorization
        regular_names = {img.get('name', '') for img in regular_images}
        avant_names = {img.get('name', '') for img in avant_images}
        apres_names = {img.get('name', '') for img in apres_images}

        for image_info in intervention.get('images', []):
            try:
                # Download image from Google Chat
                image_bytes = self.download_image_from_chat(image_info, space_id)
                if not image_bytes:
                    continue

                # Upload to Notion
                filename = image_info.get('name', f"image_{len(notion_image_urls)}")
                notion_url = self.upload_image_to_notion(image_bytes, filename)

                if notion_url:
                    notion_image_urls.append(notion_url)

                    # Categorize by matching with original attachment
                    image_name = image_info.get('name', '')
                    if image_name in regular_names:
                        notion_regular_images.append(notion_url)
                    elif image_name in avant_names:
                        notion_avant_images.append(notion_url)
                    elif image_name in apres_names:
                        notion_apres_images.append(notion_url)

            except Exception as e:
                print(f"Error processing image {image_info.get('name', 'unknown')}: {e}")
                continue

        # Store categorized notion URLs in intervention
        intervention['notion_regular_images'] = notion_regular_images
        intervention['notion_avant_images'] = notion_avant_images
        intervention['notion_apres_images'] = notion_apres_images

        print(f"📊 Processed images: {len(notion_regular_images)} regular, {len(notion_avant_images)} avant, {len(notion_apres_images)} après")

        return notion_image_urls

    def create_image_blocks_for_notion(self, image_urls: List[str]) -> List[Dict[str, Any]]:
        """
        Create Notion block structures for images.

        Args:
            image_urls: List of image URLs

        Returns:
            List of Notion block dictionaries
        """
        blocks = []

        for i, image_url in enumerate(image_urls):
            # Create image block
            image_block = {
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            }

            blocks.append(image_block)

            # Add caption if multiple images
            if len(image_urls) > 1:
                caption_block = {
                    "type": "text",
                    "text": {
                        "content": f"Photo {i + 1}",
                        "link": None
                    },
                    "annotations": {
                        "bold": False,
                        "italic": True,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    }
                }
                blocks.append(caption_block)

        return blocks

    def get_image_metadata(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Extract metadata from an image.

        Args:
            image_bytes: Image content as bytes

        Returns:
            Dictionary with image metadata
        """
        try:
            image = Image.open(BytesIO(image_bytes))

            metadata = {
                'width': image.width,
                'height': image.height,
                'format': image.format,
                'mode': image.mode,
                'size_bytes': len(image_bytes)
            }

            # Try to get EXIF data if available
            if hasattr(image, '_getexif') and image._getexif():
                metadata['has_exif'] = True
            else:
                metadata['has_exif'] = False

            return metadata

        except Exception as e:
            print(f"Error extracting image metadata: {e}")
            return {
                'width': 0,
                'height': 0,
                'format': 'unknown',
                'mode': 'unknown',
                'size_bytes': len(image_bytes),
                'has_exif': False
            }

# Convenience functions
def download_and_upload_image(attachment_info: Dict[str, Any], space_id: str,
                            google_service, notion_client) -> Optional[str]:
    """
    Convenience function to download and upload a single image.

    Args:
        attachment_info: Google Chat attachment info
        space_id: Google Chat space ID
        google_service: Authenticated Google service
        notion_client: Notion client

    Returns:
        Notion image URL or None
    """
    handler = ImageHandler(google_service, notion_client)

    # Download image
    image_bytes = handler.download_image_from_chat(attachment_info, space_id)
    if not image_bytes:
        return None

    # Upload to Notion
    filename = attachment_info.get('name', 'image')
    return handler.upload_image_to_notion(image_bytes, filename)

def process_intervention_images_batch(interventions: List[Dict[str, Any]], space_id: str,
                                    google_service, notion_client) -> List[Dict[str, Any]]:
    """
    Process images for multiple interventions in batch.

    Args:
        interventions: List of intervention dictionaries
        space_id: Google Chat space ID
        google_service: Authenticated Google service
        notion_client: Notion client

    Returns:
        List of interventions with processed images
    """
    handler = ImageHandler(google_service, notion_client)
    processed_interventions = []

    for intervention in interventions:
        try:
            # Process images for this intervention
            notion_image_urls = handler.process_intervention_images(intervention, space_id)
            intervention['notion_images'] = notion_image_urls
            intervention['image_blocks'] = handler.create_image_blocks_for_notion(notion_image_urls)

            processed_interventions.append(intervention)

        except Exception as e:
            print(f"Error processing images for intervention: {e}")
            intervention['notion_images'] = []
            intervention['image_blocks'] = []
            processed_interventions.append(intervention)

    return processed_interventions

if __name__ == "__main__":
    # Test the image handler
    handler = ImageHandler()

    # Test image validation
    test_image_bytes = b"fake image data"
    is_valid, error = handler.validate_image(test_image_bytes)
    print(f"Image validation test: {is_valid}, {error}")

    # Test metadata extraction
    metadata = handler.get_image_metadata(test_image_bytes)
    print(f"Image metadata: {metadata}")
