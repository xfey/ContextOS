"""
macOS Native System Tray Icon for Context OS.

Uses NSStatusBar and NSStatusItem (AppKit) for native menu bar integration.
Provides PyQt5-compatible interface for seamless integration with existing code.
"""

import os
from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal

from AppKit import (
    NSStatusBar, NSImage, NSVariableStatusItemLength,
    NSFont, NSColor, NSMakeRect, NSMakeSize, NSMakePoint,
    NSCompositingOperationSourceOver
)
from Foundation import NSObject as NSObjectBase
import objc


from utils.logger import get_logger

logger = get_logger('MacOSTrayIcon')


class StatusItemDelegate(NSObjectBase):
    """
    Objective-C delegate for handling NSStatusItem click events.

    Bridges between Cocoa target-action pattern and PyQt5 signals.
    """

    def initWithCallback_(self, callback):
        """
        Initialize delegate with Python callback.

        Args:
            callback: Python function to call when status item is clicked
        """
        self = objc.super(StatusItemDelegate, self).init()
        if self is None:
            return None
        self.callback = callback
        return self

    @objc.signature(b'v@:@')
    def handleClick_(self, sender):
        """
        Handle click event from NSStatusItem.

        Called by Cocoa runtime when user clicks the status item.
        """
        if self.callback:
            try:
                self.callback()
            except Exception as e:
                logger.error(f"Error in click callback: {e}", exc_info=True)


class MacOSTrayIcon(QObject):
    """
    Native macOS menu bar icon using NSStatusBar.

    Provides PyQt5-compatible interface for seamless integration:
    - PyQt5 signal for click events
    - Similar API to QSystemTrayIcon (setIcon, setToolTip, show)
    - Native macOS rendering with template mode support

    Features:
    - Template mode for automatic light/dark mode adaptation
    - Logo + badge number display
    - Click handling via PyQt5 signals
    """

    # PyQt5 signal emitted when tray icon is clicked
    activated = pyqtSignal()

    def __init__(self, parent=None):
        """
        Initialize macOS tray icon.

        Args:
            parent: Parent QObject (typically Inbox window)
        """
        super().__init__(parent)

        self.status_bar = None
        self.status_item = None
        self.delegate = None
        self.current_tooltip = ""

        logger.info("Initializing macOS native tray icon")

        try:
            # Get system status bar
            self.status_bar = NSStatusBar.systemStatusBar()

            # Create status item with variable width
            self.status_item = self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)

            # Create delegate for handling clicks
            self.delegate = StatusItemDelegate.alloc().initWithCallback_(self._on_click)

            # Set up button to handle clicks
            button = self.status_item.button()
            if button:
                button.setTarget_(self.delegate)
                button.setAction_('handleClick:')

            logger.info("✓ macOS native tray icon initialized")

        except Exception as e:
            logger.error(f"Failed to initialize macOS tray icon: {e}", exc_info=True)
            raise

    def _on_click(self):
        """
        Internal click handler.

        Emits PyQt5 signal for compatibility with existing code.
        """
        logger.debug("Tray icon clicked")
        self.activated.emit()

    def set_icon(self, image_path: str, badge_count: int = 0):
        """
        Set tray icon image with optional badge count.

        Args:
            image_path: Path to logo image file
            badge_count: Number to display next to logo (0 = no badge)
        """
        if not self.status_item:
            logger.warning("Status item not initialized")
            return

        try:
            # Create NSImage from logo file
            image = self._create_icon_image(image_path, badge_count)

            if image:
                # Set image on button
                button = self.status_item.button()
                if button:
                    button.setImage_(image)
                    logger.debug(f"Tray icon updated (badge: {badge_count})")
            else:
                logger.warning("Failed to create icon image")

        except Exception as e:
            logger.error(f"Error setting tray icon: {e}", exc_info=True)

    def _create_icon_image(self, image_path: str, badge_count: int) -> Optional[NSImage]:
        """
        Create NSImage for tray icon with logo + optional badge number.

        Args:
            image_path: Path to logo image
            badge_count: Badge count (0 = no badge)

        Returns:
            NSImage with template mode enabled
        """
        try:
            # Load base logo image
            if not os.path.exists(image_path):
                logger.error(f"Logo image not found: {image_path}")
                return None

            logo_image = NSImage.alloc().initWithContentsOfFile_(image_path)
            if not logo_image:
                logger.error(f"Failed to load logo image: {image_path}")
                return None

            # Standard menu bar icon size
            menu_bar_size = 18.0  # macOS menu bar icons are typically 18x18 points
            side_padding = 4.0  # Padding on left and right sides

            # If no badge, resize logo and return as template with padding
            if badge_count == 0:
                # Create resized image with padding
                icon_width = menu_bar_size + (side_padding * 2)
                resized_image = NSImage.alloc().initWithSize_(NSMakeSize(icon_width, menu_bar_size))
                resized_image.lockFocus()

                # Draw original image scaled down with left padding
                dest_rect = NSMakeRect(side_padding, 0, menu_bar_size, menu_bar_size)
                logo_image.drawInRect_fromRect_operation_fraction_(
                    dest_rect,
                    NSMakeRect(0, 0, logo_image.size().width, logo_image.size().height),
                    NSCompositingOperationSourceOver,
                    1.0
                )

                resized_image.unlockFocus()
                resized_image.setTemplate_(True)
                return resized_image

            # Create badge text
            badge_text = str(badge_count) if badge_count < 100 else "99+"

            # Calculate sizes
            logo_size = menu_bar_size  # Use same size as non-badge icon
            font_size = 13
            text_spacing = 6.0  # Spacing between logo and text

            # Create font for badge number (regular weight, not bold)
            font = NSFont.systemFontOfSize_(font_size)

            # Calculate text size
            text_attributes = {
                'NSFont': font
            }
            text_size = len(badge_text) * (font_size * 0.6)  # Approximate width

            # Create new image with logo + text + padding
            total_width = side_padding + logo_size + text_spacing + text_size + side_padding
            image_size = NSMakeSize(total_width, logo_size)

            # Create composite image
            composite = NSImage.alloc().initWithSize_(image_size)
            composite.lockFocus()

            # Draw logo on the left with padding
            logo_rect = NSMakeRect(side_padding, 0, logo_size, logo_size)
            logo_image.drawInRect_fromRect_operation_fraction_(
                logo_rect,
                NSMakeRect(0, 0, logo_image.size().width, logo_image.size().height),
                NSCompositingOperationSourceOver,
                1.0
            )

            # Draw badge number on the right with spacing
            text_point = NSMakePoint(side_padding + logo_size + text_spacing, 2)
            text_attributes_dict = {
                'NSFont': font,
                'NSColor': NSColor.blackColor()  # Black text (template mode will invert)
            }

            # Draw text using NSString
            from Foundation import NSString
            ns_text = NSString.stringWithString_(badge_text)
            ns_text.drawAtPoint_withAttributes_(text_point, text_attributes_dict)

            composite.unlockFocus()

            # Enable template mode for dark mode support
            composite.setTemplate_(True)

            logger.debug(f"Created icon with badge: {badge_text}")
            return composite

        except Exception as e:
            logger.error(f"Error creating icon image: {e}", exc_info=True)
            return None

    def set_tooltip(self, tooltip: str):
        """
        Set tooltip text for tray icon.

        Args:
            tooltip: Tooltip text to display on hover
        """
        if not self.status_item:
            logger.warning("Status item not initialized")
            return

        try:
            self.current_tooltip = tooltip
            button = self.status_item.button()
            if button:
                button.setToolTip_(tooltip)
                logger.debug(f"Tooltip updated: {tooltip}")
        except Exception as e:
            logger.error(f"Error setting tooltip: {e}", exc_info=True)

    def show(self):
        """
        Show the tray icon.

        Note: NSStatusItem is visible by default when created.
        This method is provided for API compatibility with QSystemTrayIcon.
        """
        logger.debug("Tray icon show() called (already visible)")

    def hide(self):
        """
        Hide the tray icon by removing it from status bar.
        """
        if self.status_bar and self.status_item:
            self.status_bar.removeStatusItem_(self.status_item)
            logger.debug("Tray icon hidden")

    def __del__(self):
        """Clean up resources when object is destroyed."""
        if self.status_bar and self.status_item:
            try:
                self.status_bar.removeStatusItem_(self.status_item)
            except:
                pass
