"""
GUI Utilities for Context OS.

Provides utility classes and functions for the PyQt5 interface.
"""

from datetime import datetime
from typing import Optional
from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QStyledItemDelegate, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint, QSize
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QIcon, QPixmap, QFontMetrics

from models.session import Session
from utils.logger import get_logger

logger = get_logger('GUI.Utils')


def get_level_color(level: str) -> QColor:
    """
    Get color for interaction level.

    Args:
        level: Interaction level (Notify/Review)

    Returns:
        QColor: Color for the level
    """
    colors = {
        'Notify': QColor('#4A90E2'),     # Blue
        'Review': QColor('#F5A623')      # Orange
    }
    return colors.get(level, QColor('#4A90E2'))


def create_icon_with_badge(image_path: str, badge_count: int = 0) -> QIcon:
    """
    Create a QIcon from SVG or PNG, or a text-based icon showing unread count.

    On macOS, the icon is created as a template image that automatically
    adapts to light/dark menu bar appearance.

    Args:
        image_path: Path to the SVG or PNG file (used when badge_count = 0)
        badge_count: Number to show in badge (0 = show logo, >0 = show "δN" text)

    Returns:
        QIcon: Logo icon (count=0) or text icon "δN" (count>0), both in template mode
    """
    # Create pixmap for the icon (use reasonable size for system tray)
    icon_size = 64
    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # When count > 0: show text-based icon "δN" instead of logo
    if badge_count > 0:
        # Format count text (max 99+)
        count_text = str(badge_count) if badge_count < 100 else "99+"

        # Set up fonts - delta in regular, number in bold
        font_size = 48

        # Regular font for delta
        delta_font = QFont()
        delta_font.setPixelSize(font_size)
        delta_font.setBold(False)

        # Bold font for number
        number_font = QFont()
        number_font.setPixelSize(font_size)
        number_font.setBold(True)

        # Calculate text widths to center properly
        delta_metrics = QFontMetrics(delta_font)
        number_metrics = QFontMetrics(number_font)

        delta_width = delta_metrics.horizontalAdvance("δ")
        number_width = number_metrics.horizontalAdvance(count_text)
        total_width = delta_width + number_width

        # Calculate starting x position to center the combined text
        start_x = (icon_size - total_width) // 2

        # Draw text in black (template mode will auto-invert for dark mode)
        painter.setPen(QColor(0, 0, 0))  # Black

        # Draw delta (regular weight)
        painter.setFont(delta_font)
        painter.drawText(start_x, icon_size // 2 + font_size // 3, "δ")

        # Draw number (bold)
        painter.setFont(number_font)
        painter.drawText(start_x + delta_width, icon_size // 2 + font_size // 3, count_text)

        logger.debug(f"Created text-based icon: δ{count_text} (delta: regular, number: bold)")
    else:
        # When count = 0: show regular logo (original behavior)
        try:
            # assert image_path.lower().endswith('.png')
            logo_pixmap = QPixmap(image_path)
            if not logo_pixmap.isNull():
                # Scale to fit icon size while maintaining aspect ratio
                scaled_pixmap = logo_pixmap.scaled(
                    icon_size, icon_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                # Center the scaled pixmap
                x = (icon_size - scaled_pixmap.width()) // 2
                y = (icon_size - scaled_pixmap.height()) // 2
                painter.drawPixmap(x, y, scaled_pixmap)
            else:
                logger.warning(f"Failed to load PNG: {image_path}, using fallback")
                # Fallback: draw a simple circle
                painter.setBrush(QColor('#4A90E2'))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(8, 8, 48, 48)
        except Exception as e:
            logger.error(f"Error loading image: {e}, using fallback icon")
            # Fallback: draw a simple circle
            painter.setBrush(QColor('#4A90E2'))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 48, 48)

    painter.end()

    # Create QIcon from pixmap
    icon = QIcon(pixmap)

    # Enable template mode on macOS for automatic light/dark mode adaptation
    # This tells macOS to treat the icon as a template that should be
    # colorized based on the menu bar appearance
    import sys
    if sys.platform == 'darwin':
        # Set the pixmap as a mask to enable template mode
        # This makes macOS automatically invert colors based on menu bar appearance
        icon.setIsMask(True)
        logger.debug("Icon set as template (mask mode) for macOS menu bar")

    return icon


class SessionItemDelegate(QStyledItemDelegate):
    """Custom delegate to paint session items with red dot and formatted text."""

    def paint(self, painter, option, index):
        """Paint the item with custom formatting."""
        # Don't call super().paint() - we'll do custom painting
        painter.save()

        # Draw background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(235, 235, 235))
        else:
            # Get background color from item
            bg_color = index.data(Qt.BackgroundRole)
            if bg_color:
                painter.fillRect(option.rect, bg_color)

        # Get the item
        item = index.data(Qt.UserRole)
        if item and hasattr(item, 'session'):
            session = item.session

            # Draw vertical colored line on the left (height spans title + datetime)
            level_color = get_level_color(session.level)
            pen = QPen(level_color, 3)  # 3px thickness
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            line_x = option.rect.left() + 4
            line_y_start = option.rect.top() + 6
            line_y_end = option.rect.bottom() - 6
            painter.drawLine(line_x, line_y_start, line_x, line_y_end)

            # Draw red dot for unread sessions (fixed position on the right)
            if not session.is_read:
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 59, 48))  # Red
                # Use fixed position relative to panel width (250px) to keep dot always visible
                dot_x = 250 - 12  # Fixed position at right edge of panel
                dot_y = option.rect.top() + option.rect.height() // 2
                painter.drawEllipse(QPoint(dot_x, dot_y), 4, 4)

            # Get text content
            text = index.data(Qt.DisplayRole)
            if text:
                # Split into title and datetime
                lines = text.split('\n')
                title = lines[0].strip() if lines else ""
                datetime_str = lines[-1].strip() if len(lines) > 1 else ""

                # Get text color (use black if selected, otherwise use item color)
                if option.state & QStyle.State_Selected:
                    # When selected, always use black for better contrast
                    painter.setPen(QColor(0, 0, 0))  # Black
                else:
                    # When not selected, use the item's foreground color
                    fg_color = index.data(Qt.ForegroundRole)
                    if fg_color:
                        # fg_color might be QBrush or QColor
                        if hasattr(fg_color, 'color'):
                            painter.setPen(fg_color.color())
                        else:
                            painter.setPen(fg_color)
                    else:
                        painter.setPen(option.palette.text().color())

                # Draw title (shifted right to account for vertical line)
                title_font = QFont()
                title_font.setBold(False)
                title_font.setPointSize(15)
                painter.setFont(title_font)

                # Calculate available width for title text
                # Reserve space for: left margin (16px) + right margin (16px)
                # If unread, reserve additional space for red dot (16px)
                left_margin = 16
                right_margin = 16
                if not session.is_read:
                    right_margin += 16  # Extra space for red dot
                available_width = 250 - left_margin - right_margin

                # Elide text if too long (add ellipsis "...")
                metrics = QFontMetrics(title_font)
                elided_title = metrics.elidedText(title, Qt.ElideRight, available_width)

                title_rect = QRect(option.rect.left() + left_margin, option.rect.top() + 7,
                                   available_width, 20)
                painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, elided_title)

                # Draw datetime (shifted right to align with title)
                datetime_font = QFont()
                datetime_font.setBold(False)
                datetime_font.setPointSize(11)
                painter.setFont(datetime_font)
                datetime_rect = QRect(option.rect.left() + 16, option.rect.top() + 28,
                                      option.rect.width() - 30, 20)
                painter.drawText(datetime_rect, Qt.AlignLeft | Qt.AlignTop, datetime_str)

        painter.restore()

    def sizeHint(self, option, index):
        """Return the size hint for items."""
        # Make items taller (about 25% more than default)
        size = super().sizeHint(option, index)
        return QSize(size.width(), 48)  # Fixed height for consistent appearance


class SessionListItem(QListWidgetItem):
    """
    Custom list item for displaying sessions in the inbox.

    Shows session title, timestamp, and status badge.
    """

    def __init__(self, session: Session):
        """
        Initialize session list item.

        Args:
            session: Session object to display
        """
        super().__init__()
        self.session = session

        # Store reference in UserRole for delegate
        self.setData(Qt.UserRole, self)

        self._update_display()

    def _update_display(self):
        """Update the display text and styling based on session state."""
        # Get session info
        level = self.session.level
        status = self.session.status
        created_at = self.session.metadata.get('created_at')

        # Format timestamp
        time_str = format_timestamp(created_at)

        # Build display text - delegate will parse and format this
        # Format: title\ndatetime (delegate will extract and format separately)
        display_text = f"{self.session.title}\n{time_str}"
        self.setText(display_text)

        # Set styling based on status
        if status == 'completed':
            # Gray out completed items
            self.setBackground(QColor(245, 245, 245))  # Light gray background
            self.setForeground(QColor(150, 150, 150))  # Gray text
        elif status == 'error':
            self.setBackground(QColor(255, 240, 240))  # Light red
            self.setForeground(QColor(180, 50, 50))    # Dark red text
        elif status == 'active':
            self.setBackground(QColor(255, 255, 255))  # White
            self.setForeground(QColor(0, 0, 0))        # Black text
        else:  # pending
            self.setBackground(QColor(255, 255, 255))  # White
            self.setForeground(QColor(0, 0, 0))        # Black text

    def _get_status_badge(self, status: str) -> str:
        """
        Get status badge emoji.

        Args:
            status: Session status

        Returns:
            str: Status badge emoji
        """
        badges = {
            'pending': '⏳',
            'active': '▶️',
            'completed': '✅',
            'error': '❌'
        }
        return badges.get(status, '●')

    def update_session(self, session: Session):
        """
        Update the session and refresh display.

        Args:
            session: Updated session object
        """
        self.session = session
        self._update_display()


class SessionListWidget(QListWidget):
    """
    Custom list widget for displaying session items.

    Provides enhanced styling and selection handling.
    """

    # Signal emitted when session is selected
    session_selected = pyqtSignal(Session)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize session list widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI styling and behavior."""
        # Enable selection
        self.setSelectionMode(QListWidget.SingleSelection)

        # Set fixed width to prevent horizontal expansion
        self.setFixedWidth(250)

        # Disable horizontal scrollbar since we have fixed width
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Apply custom delegate for rendering items with formatting
        self.setItemDelegate(SessionItemDelegate(self))

        # Connect selection signal
        self.itemSelectionChanged.connect(self._on_selection_changed)

        logger.debug("SessionListWidget initialized")

    def _on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.selectedItems()
        if selected_items:
            item = selected_items[0]
            if isinstance(item, SessionListItem):
                logger.debug(f"Session selected: {item.session.metadata.get('uuid')}")
                self.session_selected.emit(item.session)

    def add_session(self, session: Session) -> SessionListItem:
        """
        Add a session to the list.

        Args:
            session: Session to add

        Returns:
            SessionListItem: The created list item
        """
        item = SessionListItem(session)
        self.insertItem(0, item)  # Add to top
        logger.debug(f"Added session to list: {session.metadata.get('uuid')}")
        return item

    def update_session_item(self, session_id: str, session: Session):
        """
        Update an existing session item.

        Args:
            session_id: UUID of session to update
            session: Updated session object
        """
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, SessionListItem):
                if item.session.metadata.get('uuid') == session_id:
                    item.update_session(session)
                    logger.debug(f"Updated session item: {session_id}")
                    return

        logger.warning(f"Session item not found for update: {session_id}")

    def remove_session(self, session_id: str):
        """
        Remove a session from the list.

        Args:
            session_id: UUID of session to remove
        """
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, SessionListItem):
                if item.session.metadata.get('uuid') == session_id:
                    self.takeItem(i)
                    logger.debug(f"Removed session: {session_id}")
                    return

        logger.warning(f"Session not found for removal: {session_id}")

    def clear_all(self):
        """Clear all sessions from the list."""
        count = self.count()
        self.clear()
        logger.info(f"Cleared {count} sessions from list")

    def select_session_by_id(self, session_id: str):
        """
        Select a session by its ID.

        This method finds the session item in the list and selects it,
        which triggers the session_selected signal and displays the session.

        Args:
            session_id: UUID of the session to select
        """
        for i in range(self.count()):
            item = self.item(i)
            if isinstance(item, SessionListItem):
                if item.session.metadata.get('uuid') == session_id:
                    # Select the item
                    self.setCurrentItem(item)
                    logger.debug(f"Selected session in list: {session_id}")
                    return

        logger.warning(f"Session not found for selection: {session_id}")


def format_timestamp(dt) -> str:
    """
    Format timestamp for display.

    Args:
        dt: Datetime object or ISO string

    Returns:
        str: Formatted time string (e.g., "14:39", "Yesterday 11:04", "Oct 28")
    """
    if dt is None:
        return ""

    # Convert to datetime if string
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt

    if not isinstance(dt, datetime):
        return str(dt)

    # Get current time
    now = datetime.now()

    # Handle timezone-aware datetimes
    if dt.tzinfo is not None and now.tzinfo is None:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    elif dt.tzinfo is None and now.tzinfo is not None:
        dt = dt.replace(tzinfo=now.tzinfo)

    try:
        # Check if same day (today)
        if dt.date() == now.date():
            return dt.strftime("%H:%M")

        # Check if yesterday
        yesterday = now.date()
        from datetime import timedelta
        yesterday = now - timedelta(days=1)
        if dt.date() == yesterday.date():
            return dt.strftime("Yesterday %H:%M")

        # Earlier dates - show date only
        return dt.strftime("%b %d")
    except (TypeError, AttributeError):
        # If comparison fails, just format the time
        return dt.strftime("%H:%M")


def get_level_icon(level: str) -> str:
    """
    Get icon/emoji for interaction level.

    Args:
        level: Interaction level (Notify/Review)

    Returns:
        str: Icon emoji
    """
    icons = {
        'Notify': '📢',
        'Review': '💬'
    }
    return icons.get(level, '●')


def get_status_color(status: str) -> QColor:
    """
    Get color for session status.

    Args:
        status: Session status

    Returns:
        QColor: Color for status
    """
    colors = {
        'pending': QColor(200, 200, 200),     # Gray
        'active': QColor(100, 150, 255),      # Blue
        'completed': QColor(100, 200, 100),   # Green
        'error': QColor(255, 100, 100)        # Red
    }
    return colors.get(status, QColor(128, 128, 128))
