"""
Base adapter classes for Context OS.

Provides abstract base classes for event and stream data adapters.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from models.signal import Signal
from utils.logger import get_logger

logger = get_logger('Adapter')


class BaseAdapter(ABC):
    """
    Abstract base class for all adapters.

    Adapters are responsible for collecting data from various sources
    and transforming them into standardized Signal objects.
    """

    def __init__(self, name: str, config: Dict[str, Any], pipeline_callback: Optional[Callable] = None):
        """
        Initialize the base adapter.

        Args:
            name: Adapter name
            config: Adapter configuration dictionary
            pipeline_callback: Callback function to emit signals to pipeline
        """
        self.name = name
        self.config = config
        self.pipeline_callback = pipeline_callback
        self.is_running = False

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the adapter.

        This method must be implemented by subclasses to set up
        the data collection mechanism (e.g., event listeners, stream capture devices).
        """
        pass

    def start(self) -> None:
        """
        Start data collection.

        Initializes the adapter and begins collecting data.
        """
        if self.is_running:
            logger.warning(f"Adapter '{self.name}' is already running")
            return

        logger.info(f"Starting adapter: {self.name}")
        try:
            # Set is_running BEFORE initialize() to avoid race condition
            # (initialize() may start threads that check this flag)
            self.is_running = True
            self.initialize()
            logger.info(f"Adapter '{self.name}' started successfully")
        except Exception as e:
            # If initialization fails, reset the flag
            self.is_running = False
            logger.error(f"Failed to start adapter '{self.name}': {e}")
            raise

    def stop(self) -> None:
        """
        Stop data collection.

        Stops the adapter and cleans up resources.
        """
        if not self.is_running:
            logger.warning(f"Adapter '{self.name}' is not running")
            return

        logger.info(f"Stopping adapter: {self.name}")
        self.is_running = False
        logger.info(f"Adapter '{self.name}' stopped successfully")

    def get_config(self) -> Dict[str, Any]:
        """
        Get adapter configuration.

        Returns:
            dict: Adapter configuration
        """
        return self.config

    def emit_signal(self, signal: Signal) -> None:
        """
        Emit a signal to the pipeline.

        Validates the signal and sends it to the pipeline via callback.

        Args:
            signal: Signal object to emit
        """
        if not self._validate_signal(signal):
            logger.error(f"Invalid signal from adapter '{self.name}', not emitting")
            return

        if self.pipeline_callback is None:
            logger.warning(f"No pipeline callback set for adapter '{self.name}'")
            return

        logger.debug(f"Adapter '{self.name}' emitting signal: {signal.metadata.get('uuid')}")
        try:
            self.pipeline_callback(signal)
        except Exception as e:
            logger.error(f"Error emitting signal from adapter '{self.name}': {e}")

    def _validate_signal(self, signal: Signal) -> bool:
        """
        Validate that a signal has the required format.

        Args:
            signal: Signal object to validate

        Returns:
            bool: True if signal is valid, False otherwise
        """
        try:
            # Check that signal is a Signal instance
            if not isinstance(signal, Signal):
                logger.error(f"Signal must be a Signal instance, got {type(signal)}")
                return False

            # Check required fields
            if not hasattr(signal, 'source') or not signal.source:
                logger.error("Signal missing 'source' field")
                return False

            if not hasattr(signal, 'type') or not signal.type:
                logger.error("Signal missing 'type' field")
                return False

            if not hasattr(signal, 'content'):
                logger.error("Signal missing 'content' field")
                return False

            if not hasattr(signal, 'metadata') or not signal.metadata:
                logger.error("Signal missing 'metadata' field")
                return False

            # Check metadata fields
            if 'uuid' not in signal.metadata:
                logger.error("Signal metadata missing 'uuid'")
                return False

            if 'timestamp' not in signal.metadata:
                logger.error("Signal metadata missing 'timestamp'")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating signal: {e}")
            return False


class EventAdapter(BaseAdapter):
    """
    Base class for event-based adapters.

    Event adapters handle discrete state changes or user actions
    (e.g., clipboard updates, file saves).
    """

    def on_event(self, raw_event: Any) -> None:
        """
        Handle incoming event.

        This is the entry point for event callbacks.

        Args:
            raw_event: Raw event data from the event source
        """
        if not self.is_running:
            return

        # Apply filtering rules
        if not self._filter_event(raw_event):
            logger.debug(f"Event filtered out by adapter '{self.name}'")
            return

        # Transform to signal
        signal = self._transform_to_signal(raw_event)
        if signal is not None:
            self.emit_signal(signal)

    def _filter_event(self, raw_event: Any) -> bool:
        """
        Apply filtering rules to event.

        Subclasses should implement this to apply noise reduction,
        deduplication, and other filtering logic.

        Args:
            raw_event: Raw event data

        Returns:
            bool: True if event should be processed, False if filtered out
        """
        # Default: accept all events
        return True

    @abstractmethod
    def _transform_to_signal(self, raw_event: Any) -> Optional[Signal]:
        """
        Transform raw event to Signal format.

        Subclasses must implement this to convert raw event data
        into standardized Signal objects.

        Args:
            raw_event: Raw event data

        Returns:
            Signal object or None if transformation fails
        """
        pass


class StreamAdapter(BaseAdapter):
    """
    Base class for stream-based adapters.

    Stream adapters handle continuous data flows
    (e.g., screen captures, audio input).
    """

    def __init__(self, name: str, config: Dict[str, Any], pipeline_callback: Optional[Callable] = None):
        """
        Initialize the stream adapter.

        Args:
            name: Adapter name
            config: Adapter configuration
            pipeline_callback: Callback function to emit signals
        """
        super().__init__(name, config, pipeline_callback)
        self.buffer = []
        self.buffer_size = config.get('buffer_size', 10)
        self.is_capturing = False

    def start_capture(self) -> None:
        """
        Start capturing stream data to internal buffer.

        Subclasses should implement the actual capture logic.
        """
        if self.is_capturing:
            logger.warning(f"Stream adapter '{self.name}' is already capturing")
            return

        logger.info(f"Starting stream capture for adapter: {self.name}")
        self.is_capturing = True

    def stop_capture(self) -> None:
        """
        Stop capturing stream data.
        """
        if not self.is_capturing:
            logger.warning(f"Stream adapter '{self.name}' is not capturing")
            return

        logger.info(f"Stopping stream capture for adapter: {self.name}")
        self.is_capturing = False

    def stop(self) -> None:
        """
        Stop the stream adapter and clean up.
        """
        self.stop_capture()
        super().stop()

    @abstractmethod
    def _sample_stream(self, interval: float) -> Any:
        """
        Sample stream data at specified interval.

        Subclasses must implement this to extract data from the stream.

        Args:
            interval: Sampling interval in seconds

        Returns:
            Sampled stream data
        """
        pass

    def _deduplicate(self, stream_data: Any) -> Any:
        """
        Deduplicate and compress stream data.

        For example, remove consecutive similar screenshots.

        Args:
            stream_data: Raw stream data

        Returns:
            Deduplicated stream data
        """
        # Default: return data as-is
        # Subclasses can implement deduplication logic
        return stream_data

    @abstractmethod
    def _transform_to_signal(self, stream_data: Any) -> Optional[Signal]:
        """
        Transform stream segment to Signal format.

        Subclasses must implement this to convert stream data
        into standardized Signal objects.

        Args:
            stream_data: Stream data segment

        Returns:
            Signal object or None if transformation fails
        """
        pass

    def get_buffer_status(self) -> Dict[str, Any]:
        """
        Get buffer status information.

        Returns:
            dict: Buffer status with size and usage information
        """
        return {
            'current_size': len(self.buffer),
            'max_size': self.buffer_size,
            'usage_percent': (len(self.buffer) / self.buffer_size * 100) if self.buffer_size > 0 else 0,
            'is_full': len(self.buffer) >= self.buffer_size
        }
