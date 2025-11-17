"""
Clipboard adapter for Context OS.

Monitors system clipboard for text and image changes and emits signals.
Uses native macOS NSPasteboard API for better Unicode support and efficiency.

Supports:
- Text-only clipboard content
- Image-only clipboard content (PNG, TIFF)
- Multimodal clipboard content (text + image)

Image processing:
- Validates aspect ratio (max 200:1) and minimum size (10px smaller edge)
- Resizes images with longer edge > 1024px
- Compresses images to < 1MB
- Converts TIFF to PNG for efficiency
"""

import time
import threading
import base64
import io
from typing import Any, Optional, Dict

from PIL import Image
from AppKit import NSPasteboard, NSPasteboardTypeString, NSPasteboardTypePNG, NSPasteboardTypeTIFF

from adapters.base import EventAdapter
from models.signal import Signal
from utils.logger import get_logger

logger = get_logger('ClipboardAdapter')


class ClipboardAdapter(EventAdapter):
    """
    Adapter for monitoring system clipboard changes.

    Uses macOS NSPasteboard API for:
    - Native Unicode/UTF-8 support (fixes Chinese character issues)
    - Efficient change detection via changeCount()
    - Foundation for future image support

    Monitors clipboard for text updates and emits Signal objects
    when new content is detected.
    """

    def __init__(self, name: str, config: Dict[str, Any], pipeline_callback=None):
        """
        Initialize clipboard adapter.

        Args:
            name: Adapter name
            config: Configuration dictionary from sources.yaml
            pipeline_callback: Callback to emit signals to pipeline
        """
        super().__init__(name, config, pipeline_callback)
        self.pasteboard = None
        self.last_change_count = -1
        self.last_clipboard_content = ""
        self.poll_interval = config.get('poll_interval', 1)
        self.filters = config.get('filters', {})
        self.monitor_thread = None

    def initialize(self) -> None:
        """
        Initialize clipboard monitoring.

        Sets up NSPasteboard and polling thread to monitor clipboard changes.
        """
        logger.info(f"Initializing NSPasteboard clipboard adapter with poll_interval={self.poll_interval}s")

        try:
            # Get general pasteboard (system clipboard)
            self.pasteboard = NSPasteboard.generalPasteboard()

            # Get initial change count and content to avoid triggering on startup
            self.last_change_count = self.pasteboard.changeCount()
            initial_text = self.pasteboard.stringForType_(NSPasteboardTypeString)
            self.last_clipboard_content = initial_text if initial_text else ""

            logger.info(f"NSPasteboard initialized - changeCount: {self.last_change_count}, "
                       f"content length: {len(self.last_clipboard_content)}")

        except Exception as e:
            logger.error(f"Failed to initialize NSPasteboard: {e}")
            raise

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Clipboard monitoring thread started")

    def _monitor_loop(self) -> None:
        """
        Main monitoring loop that polls clipboard at intervals.

        Uses NSPasteboard.changeCount() for efficient change detection,
        then retrieves actual content only when changes are detected.

        This runs in a separate thread and checks for clipboard changes.
        """
        logger.info("Clipboard monitor loop started")

        while self.is_running:
            try:
                if not self.pasteboard:
                    logger.warning("Pasteboard not initialized, skipping check")
                    time.sleep(self.poll_interval)
                    continue

                # Check if clipboard has changed using changeCount()
                # This is much more efficient than comparing strings
                current_change_count = self.pasteboard.changeCount()

                if current_change_count != self.last_change_count:
                    logger.debug(f"Clipboard changed - changeCount: {self.last_change_count} → {current_change_count}")

                    # Try to get text content
                    text_content = self.pasteboard.stringForType_(NSPasteboardTypeString)

                    # Try to get image content
                    image_data = None
                    mime_type = None

                    # Check for PNG first (more common)
                    pasteboard_types = self.pasteboard.types()
                    if pasteboard_types.containsObject_(NSPasteboardTypePNG):
                        image_data = self.pasteboard.dataForType_(NSPasteboardTypePNG)
                        mime_type = 'image/png'
                        logger.debug("Detected PNG image in clipboard")
                    elif pasteboard_types.containsObject_(NSPasteboardTypeTIFF):
                        image_data = self.pasteboard.dataForType_(NSPasteboardTypeTIFF)
                        mime_type = 'image/tiff'
                        logger.debug("Detected TIFF image in clipboard")

                    # Convert NSData to bytes if image found
                    if image_data is not None:
                        image_data = bytes(image_data)

                    # Determine what we have and create appropriate event
                    has_text = text_content is not None and len(str(text_content).strip()) > 0
                    has_image = image_data is not None

                    if not has_text and not has_image:
                        # Clipboard contains something else (file, etc.)
                        logger.debug("Clipboard contains no text or image data, skipping")
                        self.last_change_count = current_change_count
                        time.sleep(self.poll_interval)
                        continue

                    # Check if content actually changed (for text-only case)
                    if has_text and not has_image:
                        if text_content == self.last_clipboard_content:
                            logger.debug("changeCount changed but text content identical, skipping")
                            self.last_change_count = current_change_count
                            time.sleep(self.poll_interval)
                            continue

                    # Create event data structure
                    event_data = {
                        'text': str(text_content) if has_text else None,
                        'image': image_data if has_image else None,
                        'mime_type': mime_type
                    }

                    # Log what we found
                    if has_text and has_image:
                        logger.debug(f"Clipboard has multimodal content: text ({len(text_content)} chars) + image ({len(image_data)} bytes, {mime_type})")
                    elif has_image:
                        logger.debug(f"Clipboard has image only: {len(image_data)} bytes, {mime_type}")
                    elif has_text:
                        logger.debug(f"Clipboard has text only: {len(text_content)} chars")
                        logger.debug(f"Content preview: {text_content[:100]}...")

                    # Trigger event callback with structured data
                    self.on_event(event_data)

                    # Update tracking variables
                    if has_text:
                        self.last_clipboard_content = text_content
                    else:
                        self.last_clipboard_content = ""

                    # Always update change count
                    self.last_change_count = current_change_count

                # Sleep for poll interval
                time.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in clipboard monitor loop: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        logger.info("Clipboard monitor loop stopped")

    def stop(self) -> None:
        """
        Stop clipboard monitoring and clean up.
        """
        logger.info("Stopping clipboard adapter")
        super().stop()

        # Wait for monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            logger.info("Clipboard monitor thread stopped")

        # Release pasteboard reference
        self.pasteboard = None

    def _validate_image(self, image_data: bytes, mime_type: str) -> Optional[Image.Image]:
        """
        Validate image data according to requirements.

        Requirements:
        1. Aspect ratio no more than 200:1
        2. Smaller edge at least 10px

        Args:
            image_data: Raw image bytes from NSPasteboard
            mime_type: MIME type (e.g., 'image/png', 'image/tiff')

        Returns:
            PIL Image object if valid, None if invalid
        """
        try:
            # Load image with PIL
            image = Image.open(io.BytesIO(image_data))
            width, height = image.size

            logger.debug(f"Image loaded: {width}x{height}px, format: {image.format}, mode: {image.mode}")

            # Check smaller edge >= 10px
            smaller_edge = min(width, height)
            if smaller_edge < 10:
                logger.debug(f"Image rejected: smaller edge ({smaller_edge}px) < 10px")
                return None

            # Check aspect ratio <= 200:1
            longer_edge = max(width, height)
            aspect_ratio = longer_edge / smaller_edge
            if aspect_ratio > 200:
                logger.debug(f"Image rejected: aspect ratio ({aspect_ratio:.2f}:1) > 200:1")
                return None

            logger.debug(f"Image validation passed: {width}x{height}px, aspect ratio: {aspect_ratio:.2f}:1")
            return image

        except Exception as e:
            logger.error(f"Error validating image: {e}", exc_info=True)
            return None

    def _process_image(self, pil_image: Image.Image, original_mime_type: str) -> Optional[str]:
        """
        Process image with resizing and compression.

        Requirements:
        1. If longer edge > 1024px, resize to 1024px (keep aspect ratio)
        2. Compress until size < 1MB
        3. Convert TIFF to PNG for efficiency

        Args:
            pil_image: PIL Image object
            original_mime_type: Original MIME type (e.g., 'image/png', 'image/tiff')

        Returns:
            Data URL string (data:image/{type};base64,{base64_string}) or None if failed
        """
        try:
            width, height = pil_image.size
            logger.debug(f"Processing image: {width}x{height}px, original format: {original_mime_type}")

            # Determine output format
            # Convert TIFF to PNG, keep PNG as PNG, others default to PNG
            if 'tiff' in original_mime_type.lower():
                output_format = 'PNG'
                output_mime = 'image/png'
                logger.debug("Converting TIFF to PNG")
            elif 'png' in original_mime_type.lower():
                output_format = 'PNG'
                output_mime = 'image/png'
            else:
                # Default to PNG for other formats
                output_format = 'PNG'
                output_mime = 'image/png'

            # Convert image mode if necessary (e.g., RGBA, P mode)
            # PNG supports RGBA, but for compression we might want RGB for non-transparent images
            if pil_image.mode in ('RGBA', 'LA', 'P'):
                # Keep transparency support
                if output_format == 'PNG':
                    # PNG supports alpha, keep RGBA
                    if pil_image.mode == 'P':
                        pil_image = pil_image.convert('RGBA')
                else:
                    # JPEG doesn't support alpha, convert to RGB
                    if pil_image.mode in ('RGBA', 'LA'):
                        # Create white background
                        background = Image.new('RGB', pil_image.size, (255, 255, 255))
                        if pil_image.mode == 'RGBA':
                            background.paste(pil_image, mask=pil_image.split()[3])
                        else:
                            background.paste(pil_image, mask=pil_image.split()[1])
                        pil_image = background
                    else:
                        pil_image = pil_image.convert('RGB')
            elif pil_image.mode not in ('RGB', 'RGBA', 'L'):
                # Convert other modes to RGB
                pil_image = pil_image.convert('RGB')

            # Resize if longer edge > 1024px
            longer_edge = max(width, height)
            if longer_edge > 1024:
                scale_factor = 1024 / longer_edge
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"Resized image: {width}x{height}px → {new_width}x{new_height}px")
                width, height = new_width, new_height

            # Compress until size < 1MB
            max_size_bytes = 1 * 1024 * 1024  # 1MB
            quality = 95
            min_quality = 50

            while quality >= min_quality:
                # Save to BytesIO buffer
                buffer = io.BytesIO()

                if output_format == 'PNG':
                    # PNG uses optimize parameter instead of quality
                    # For better compression, we can also reduce quality indirectly
                    pil_image.save(buffer, format=output_format, optimize=True)
                else:
                    # JPEG uses quality parameter
                    pil_image.save(buffer, format=output_format, quality=quality, optimize=True)

                # Get size
                buffer.seek(0)
                image_bytes = buffer.getvalue()
                size_bytes = len(image_bytes)
                size_mb = size_bytes / (1024 * 1024)

                logger.debug(f"Compressed to {size_mb:.2f}MB with quality={quality}")

                # Check if under size limit
                if size_bytes < max_size_bytes:
                    logger.debug(f"Image processing complete: {width}x{height}px, {size_mb:.2f}MB, format={output_format}")

                    # Encode to base64
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')

                    # Create Data URL
                    data_url = f"data:{output_mime};base64,{base64_image}"

                    return data_url

                # If PNG and still too large, try converting to JPEG
                if output_format == 'PNG' and size_bytes >= max_size_bytes:
                    logger.debug("PNG too large, trying JPEG compression")
                    output_format = 'JPEG'
                    output_mime = 'image/jpeg'

                    # Convert RGBA to RGB for JPEG
                    if pil_image.mode == 'RGBA':
                        background = Image.new('RGB', pil_image.size, (255, 255, 255))
                        background.paste(pil_image, mask=pil_image.split()[3])
                        pil_image = background
                    elif pil_image.mode != 'RGB':
                        pil_image = pil_image.convert('RGB')

                    continue

                # Reduce quality
                quality -= 5

            # If we reach here, image is still too large even at minimum quality
            logger.warning(f"Image too large to compress below 1MB (final size: {size_mb:.2f}MB)")
            return None

        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            return None

    def _filter_event(self, raw_event: Any) -> bool:
        """
        Apply filtering rules to clipboard content.

        Filters based on:
        - min_length: Minimum text length (for text content)
        - Image validation happens in _transform_to_signal via _validate_image

        Args:
            raw_event: Dictionary with 'text', 'image', and 'mime_type' keys
                      or legacy string for backward compatibility

        Returns:
            bool: True if event should be processed, False if filtered out
        """
        # Handle legacy string input for backward compatibility
        if isinstance(raw_event, str):
            # Check minimum length
            min_length = self.filters.get('min_length', 0)
            if len(raw_event) < min_length:
                logger.debug(f"Filtered: text length {len(raw_event)} < min_length {min_length}")
                return False

            max_length = self.filters.get('max_length', 0)
            if len(raw_event) > max_length:
                logger.debug(f"Filtered: text length {len(raw_event)} > max_length {max_length}")
                return False

            # If content is empty or only whitespace
            if not raw_event.strip():
                logger.debug("Filtered: clipboard content is empty or whitespace")
                return False

            logger.debug("Text content passed all filters")
            return True

        # Handle new structured event data
        if not isinstance(raw_event, dict):
            logger.debug(f"Filtered: invalid event type {type(raw_event)}")
            return False

        text_data = raw_event.get('text')
        image_data = raw_event.get('image')

        has_text = text_data is not None
        has_image = image_data is not None

        # Must have at least text or image
        if not has_text and not has_image:
            logger.debug("Filtered: no text or image data")
            return False

        # Filter text if present
        if has_text:
            min_length = self.filters.get('min_length', 0)
            if len(text_data) < min_length:
                logger.debug(f"Filtered: text length {len(text_data)} < min_length {min_length}")
                # If we also have image, allow it through
                if not has_image:
                    return False
                # If we have both, just log and continue (image might still be valid)
                logger.debug("  But has image, continuing to validation")

            # If text is empty or only whitespace
            if not text_data.strip():
                logger.debug("Text is empty or whitespace")
                # If we also have image, allow it through
                if not has_image:
                    logger.debug("Filtered: no valid text and no image")
                    return False
                # If we have both, just log and continue
                logger.debug("  But has image, continuing to validation")

        # Image validation will happen in _transform_to_signal via _validate_image
        # We just check if image data exists here
        if has_image and not has_text:
            logger.debug("Image-only content, validation will happen in transform stage")

        logger.debug("Clipboard content passed initial filters")
        return True

    def _transform_to_signal(self, raw_event: Any) -> Optional[Signal]:
        """
        Transform clipboard content (text/image/multimodal) to Signal format.

        Args:
            raw_event: Dictionary with 'text', 'image', and 'mime_type' keys
                      or legacy string for backward compatibility

        Returns:
            Signal object with clipboard data (text/image/multimodal type)
        """
        try:
            # Handle legacy string input for backward compatibility
            if isinstance(raw_event, str):
                signal = Signal(
                    source='clipboard',
                    type='event',
                    content={
                        'type': 'text',
                        'data': raw_event,
                    }
                )
                logger.debug(f"Transformed text-only clipboard to Signal: {signal.metadata['uuid']}")
                return signal

            # Handle new structured event data
            if not isinstance(raw_event, dict):
                logger.error(f"Invalid raw_event type: {type(raw_event)}")
                return None

            text_data = raw_event.get('text')
            image_data = raw_event.get('image')
            mime_type = raw_event.get('mime_type')

            has_text = text_data is not None
            has_image = image_data is not None

            # Process image if present (validate and compress)
            processed_image_url = None
            if has_image:
                # Validate image
                pil_image = self._validate_image(image_data, mime_type)
                if pil_image is None:
                    logger.debug("Image validation failed, skipping image")
                    has_image = False
                else:
                    # Process image (resize and compress)
                    processed_image_url = self._process_image(pil_image, mime_type)
                    if processed_image_url is None:
                        logger.warning("Image processing failed, skipping image")
                        has_image = False

            # Create Signal based on what we have
            if has_text and has_image:
                # Multimodal: both text and image
                signal = Signal(
                    source='clipboard',
                    type='event',
                    content={
                        'type': 'multimodal',
                        'data': [text_data, processed_image_url]  # [text, image]
                    }
                )
                logger.debug(f"Transformed multimodal clipboard to Signal: {signal.metadata['uuid']}")
                logger.debug(f"  Text length: {len(text_data)} chars")
                logger.debug(f"  Image: {mime_type}, processed to Data URL")

            elif has_image:
                # Image only
                signal = Signal(
                    source='clipboard',
                    type='event',
                    content={
                        'type': 'image',
                        'data': processed_image_url
                    }
                )
                logger.debug(f"Transformed image-only clipboard to Signal: {signal.metadata['uuid']}")
                logger.debug(f"  Image: {mime_type}, processed to Data URL")

            elif has_text:
                # Text only
                signal = Signal(
                    source='clipboard',
                    type='event',
                    content={
                        'type': 'text',
                        'data': text_data,
                    }
                )
                logger.debug(f"Transformed text-only clipboard to Signal: {signal.metadata['uuid']}")
                logger.debug(f"  Text length: {len(text_data)} chars")

            else:
                # Nothing valid
                logger.debug("No valid text or image after processing, skipping")
                return None

            return signal

        except Exception as e:
            logger.error(f"Error transforming clipboard content to Signal: {e}", exc_info=True)
            return None
