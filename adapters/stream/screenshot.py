"""
Screenshot adapter for Context OS.

Continuously captures screenshots at specified intervals and emits signals.
Supports deduplication using perceptual hashing to avoid processing identical screens.

Features:
- Cross-platform screenshot capture using mss
- Perceptual hashing for deduplication
- Image validation, resizing, and compression (reuses clipboard logic)
- Configurable capture interval and resolution
- Buffer management for stream data
"""

import time
import threading
import base64
import io
from typing import Any, Optional, Dict

import mss
import imagehash
from PIL import Image

from adapters.base import StreamAdapter
from models.signal import Signal
from utils.logger import get_logger

logger = get_logger('ScreenshotAdapter')


class ScreenshotAdapter(StreamAdapter):
    """
    Adapter for capturing screenshots at regular intervals.

    Extends StreamAdapter to provide continuous screen capture functionality
    with deduplication to avoid processing identical or very similar screenshots.
    """

    def __init__(self, name: str, config: Dict[str, Any], pipeline_callback=None):
        """
        Initialize screenshot adapter.

        Args:
            name: Adapter name
            config: Configuration dictionary from sources.yaml
            pipeline_callback: Callback to emit signals to pipeline
        """
        super().__init__(name, config, pipeline_callback)

        # Configuration
        self.capture_interval = config.get('capture_interval', 30)  # seconds
        self.deduplicate_threshold = config.get('deduplicate_threshold', 0.95)
        self.resolution = config.get('resolution', None)  # e.g., "1920x1080" or None for native

        # State management
        self.sct = None  # mss screenshot instance
        self.capture_thread = None
        self.last_hash = None  # For deduplication

        logger.info(f"Screenshot adapter initialized: interval={self.capture_interval}s, "
                   f"deduplicate_threshold={self.deduplicate_threshold}, resolution={self.resolution}")

    def initialize(self) -> None:
        """
        Initialize screenshot capture.

        Sets up mss instance and starts the capture thread.
        """
        logger.info(f"Initializing screenshot adapter with capture_interval={self.capture_interval}s")

        try:
            # Initialize mss for screen capture
            self.sct = mss.mss()
            logger.info(f"mss initialized - monitors detected: {len(self.sct.monitors)}")

            # Log monitor information
            for i, monitor in enumerate(self.sct.monitors):
                if i == 0:
                    logger.debug(f"Monitor {i} (all screens): {monitor}")
                else:
                    logger.debug(f"Monitor {i}: {monitor}")

        except Exception as e:
            logger.error(f"Failed to initialize mss: {e}")
            raise

        # Start capture thread
        self.start_capture()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        logger.info("Screenshot capture thread started")

    def _capture_loop(self) -> None:
        """
        Main capture loop that takes screenshots at intervals.

        Runs in a separate thread and continuously captures screenshots,
        applies deduplication, and emits signals when screen content changes.
        """
        logger.info("Screenshot capture loop started")

        while self.is_running and self.is_capturing:
            try:
                # Capture screenshot
                screenshot_data = self._sample_stream(self.capture_interval)

                if screenshot_data is None:
                    logger.debug("Screenshot capture returned None, skipping")
                    time.sleep(self.capture_interval)
                    continue

                # Apply deduplication
                deduplicated_data = self._deduplicate(screenshot_data)

                if deduplicated_data is None:
                    logger.debug("Screenshot filtered by deduplication, skipping")
                    time.sleep(self.capture_interval)
                    continue

                # Transform to signal
                signal = self._transform_to_signal(deduplicated_data)

                if signal is not None:
                    # Emit signal to pipeline
                    self.emit_signal(signal)
                    logger.debug(f"Screenshot signal emitted: {signal.metadata['uuid']}")
                else:
                    logger.debug("Screenshot transformation returned None, skipping")

                # Sleep for capture interval
                time.sleep(self.capture_interval)

            except Exception as e:
                logger.error(f"Error in screenshot capture loop: {e}", exc_info=True)
                time.sleep(self.capture_interval)

        logger.info("Screenshot capture loop stopped")

    def stop(self) -> None:
        """
        Stop screenshot capture and clean up.
        """
        logger.info("Stopping screenshot adapter")

        # Call parent stop (which calls stop_capture())
        super().stop()

        # Wait for capture thread to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)
            logger.info("Screenshot capture thread stopped")

        # Close mss instance
        if self.sct:
            self.sct.close()
            self.sct = None
            logger.info("mss instance closed")

    def _sample_stream(self, interval: float) -> Optional[Dict[str, Any]]:
        """
        Capture a single screenshot from the primary monitor.

        Args:
            interval: Capture interval (not used directly, handled by loop)

        Returns:
            Dictionary with 'image' (PIL Image) and 'monitor_info' keys,
            or None if capture fails
        """
        try:
            if not self.sct:
                logger.warning("mss not initialized, cannot capture screenshot")
                return None

            # Capture from monitor 1 (primary monitor)
            # Monitor 0 is a special "all monitors" virtual monitor in mss
            monitor = self.sct.monitors[1]

            # Capture screenshot
            screenshot = self.sct.grab(monitor)

            # Convert to PIL Image
            # mss returns image in BGRA format
            pil_image = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')

            logger.debug(f"Screenshot captured: {pil_image.size[0]}x{pil_image.size[1]}px from monitor {monitor}")

            return {
                'image': pil_image,
                'monitor_info': monitor
            }

        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}", exc_info=True)
            return None

    def _deduplicate(self, stream_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Deduplicate screenshots using perceptual hashing.

        Compares current screenshot with previous one using dhash.
        If similarity is above threshold, returns None to skip processing.

        Args:
            stream_data: Dictionary with 'image' (PIL Image) key

        Returns:
            Original stream_data if different enough from previous,
            None if too similar (duplicate)
        """
        try:
            if stream_data is None or 'image' not in stream_data:
                return None

            pil_image = stream_data['image']

            # Calculate perceptual hash (dhash - difference hash)
            # dhash is good for detecting similar images with small differences
            current_hash = imagehash.dhash(pil_image, hash_size=8)

            # Compare with previous hash
            if self.last_hash is not None:
                # Calculate similarity (1.0 = identical, 0.0 = completely different)
                # Hash difference ranges from 0 (identical) to 64 (completely different for 8x8 hash)
                hash_diff = current_hash - self.last_hash
                max_diff = 64  # Maximum possible difference for 8x8 dhash
                similarity = 1.0 - (hash_diff / max_diff)

                logger.debug(f"Screenshot similarity: {similarity:.3f} (threshold: {self.deduplicate_threshold})")

                if similarity >= self.deduplicate_threshold:
                    logger.debug(f"Screenshot too similar to previous (similarity: {similarity:.3f}), skipping")
                    return None
                else:
                    logger.debug(f"Screenshot different enough (similarity: {similarity:.3f}), processing")
            else:
                logger.debug("First screenshot, no previous hash to compare")

            # Update last hash
            self.last_hash = current_hash

            return stream_data

        except Exception as e:
            logger.error(f"Error in deduplication: {e}", exc_info=True)
            # On error, return data to avoid blocking stream
            return stream_data

    def _validate_image(self, pil_image: Image.Image) -> bool:
        """
        Validate screenshot image according to requirements.

        Requirements (from clipboard adapter):
        1. Aspect ratio no more than 200:1
        2. Smaller edge at least 10px

        Args:
            pil_image: PIL Image object

        Returns:
            True if valid, False if invalid
        """
        try:
            width, height = pil_image.size

            # Check smaller edge >= 10px
            smaller_edge = min(width, height)
            if smaller_edge < 10:
                logger.debug(f"Image rejected: smaller edge ({smaller_edge}px) < 10px")
                return False

            # Check aspect ratio <= 200:1
            longer_edge = max(width, height)
            aspect_ratio = longer_edge / smaller_edge
            if aspect_ratio > 200:
                logger.debug(f"Image rejected: aspect ratio ({aspect_ratio:.2f}:1) > 200:1")
                return False

            logger.debug(f"Image validation passed: {width}x{height}px, aspect ratio: {aspect_ratio:.2f}:1")
            return True

        except Exception as e:
            logger.error(f"Error validating image: {e}", exc_info=True)
            return False

    def _process_image(self, pil_image: Image.Image) -> Optional[str]:
        """
        Process screenshot with resizing and compression.

        Requirements (from clipboard adapter):
        1. If longer edge > 1024px, resize to 1024px (keep aspect ratio)
        2. Compress until size < 1MB
        3. Output as PNG format

        Args:
            pil_image: PIL Image object

        Returns:
            Data URL string (data:image/png;base64,{base64_string}) or None if failed
        """
        try:
            width, height = pil_image.size
            logger.debug(f"Processing screenshot: {width}x{height}px")

            # Convert to RGB if necessary (screenshots should already be RGB)
            if pil_image.mode != 'RGB':
                logger.debug(f"Converting from {pil_image.mode} to RGB")
                pil_image = pil_image.convert('RGB')

            # Resize if longer edge > 1024px
            longer_edge = max(width, height)
            if longer_edge > 1024:
                scale_factor = 1024 / longer_edge
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"Resized screenshot: {width}x{height}px → {new_width}x{new_height}px")
                width, height = new_width, new_height

            # Compress until size < 1MB
            max_size_bytes = 1 * 1024 * 1024  # 1MB
            quality = 95
            min_quality = 50
            output_format = 'PNG'
            output_mime = 'image/png'

            while quality >= min_quality:
                # Save to BytesIO buffer
                buffer = io.BytesIO()

                if output_format == 'PNG':
                    # PNG uses optimize parameter
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
                    logger.debug(f"Screenshot processing complete: {width}x{height}px, {size_mb:.2f}MB, format={output_format}")

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
                    continue

                # Reduce quality for JPEG
                quality -= 5

            # If we reach here, image is still too large even at minimum quality
            logger.warning(f"Screenshot too large to compress below 1MB (final size: {size_mb:.2f}MB)")
            return None

        except Exception as e:
            logger.error(f"Error processing screenshot: {e}", exc_info=True)
            return None

    def _transform_to_signal(self, stream_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Transform screenshot data to Signal format.

        Args:
            stream_data: Dictionary with 'image' (PIL Image) key

        Returns:
            Signal object with screenshot data (image type)
        """
        try:
            if stream_data is None or 'image' not in stream_data:
                logger.error("Invalid stream_data: missing 'image' key")
                return None

            pil_image = stream_data['image']

            # Validate image
            if not self._validate_image(pil_image):
                logger.debug("Screenshot validation failed, skipping")
                return None

            # Process image (resize and compress)
            processed_image_url = self._process_image(pil_image)

            if processed_image_url is None:
                logger.warning("Screenshot processing failed, skipping")
                return None

            # Create Signal with image type
            signal = Signal(
                source='screenshot',
                type='stream',
                content={
                    'type': 'image',
                    'data': processed_image_url
                }
            )

            logger.debug(f"Transformed screenshot to Signal: {signal.metadata['uuid']}")
            logger.debug(f"  Image size: {pil_image.size[0]}x{pil_image.size[1]}px")

            return signal

        except Exception as e:
            logger.error(f"Error transforming screenshot to Signal: {e}", exc_info=True)
            return None
