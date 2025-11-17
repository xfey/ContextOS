"""
Renderer for Context OS.

Renders session UI based on interaction level (Notify/Review).
"""

from typing import Dict, Any, Optional, Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QPixmap
import mistune
from html import escape
import base64

from models.session import Session
from utils.logger import get_logger

logger = get_logger('Renderer')


class StatusIconWidget(QWidget):
    """
    Custom widget that draws status icons using simple lines.

    Status types:
    - completed: Dark green checkmark (✓)
    - error: Red cross (×)
    - active: Blue circle
    - pending: Gray circle
    """

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.status = status
        self.setFixedSize(20, 20)

    def paintEvent(self, event):
        """Draw the status icon using QPainter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Set color based on status
        if self.status == 'completed':
            color = QColor('#2d7d46')  # Dark green
            self._draw_checkmark(painter, color)
        elif self.status == 'error':
            color = QColor('#dc3545')  # Red
            self._draw_cross(painter, color)
        elif self.status == 'active':
            color = QColor('#007bff')  # Blue
            self._draw_circle(painter, color)
        else:  # pending
            color = QColor('#6c757d')  # Gray
            self._draw_circle(painter, color)

    def _draw_checkmark(self, painter: QPainter, color: QColor):
        """Draw a checkmark using two lines."""
        pen = QPen(color, 2.5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        # First line (bottom left to middle)
        painter.drawLine(5, 10, 8, 14)
        # Second line (middle to top right)
        painter.drawLine(8, 14, 15, 6)

    def _draw_cross(self, painter: QPainter, color: QColor):
        """Draw a cross using two lines."""
        pen = QPen(color, 2.5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        # Diagonal line from top-left to bottom-right
        painter.drawLine(6, 6, 14, 14)
        # Diagonal line from top-right to bottom-left
        painter.drawLine(14, 6, 6, 14)

    def _draw_circle(self, painter: QPainter, color: QColor):
        """Draw a filled circle."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(6, 6, 8, 8)


class Renderer:
    """
    Renderer creates UI widgets for sessions based on interaction level.

    Supports two rendering modes:
    - Notify: Display-only notification card
    - Review: Full conversation interface with input
    """

    def __init__(self):
        """Initialize the Renderer."""
        logger.info("Renderer initialized")

    def render(self, session: Session) -> QWidget:
        """
        Render a session into a widget.

        Dispatches to appropriate render method based on session level.

        Args:
            session: Session to render

        Returns:
            QWidget: Rendered widget
        """
        level = session.level
        logger.debug(f"Rendering session {session.metadata.get('uuid')} as {level}")

        if level == 'Notify':
            return self.render_notify(session)
        elif level == 'Review':
            return self.render_review(session)
        else:
            logger.warning(f"Unknown session level: {level}, using Notify")
            return self.render_notify(session)

    def render_notify(self, session: Session) -> QWidget:
        """
        Render a Notify-level session (display-only notification).

        Args:
            session: Session to render

        Returns:
            QWidget: Notification card widget
        """
        logger.debug("Rendering Notify card")

        # Create main widget
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Add header
        header = self._create_header(session)
        layout.addWidget(header)

        # Add separator (light gray split line)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("""
            QFrame {
                border: none;
                background-color: #e0e0e0;
                max-height: 1px;
            }
        """)
        layout.addWidget(separator)

        # Create scroll area for message content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Create container widget for messages
        messages_container = QWidget()
        messages_layout = QVBoxLayout()
        messages_container.setLayout(messages_layout)
        messages_layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins for alignment
        messages_layout.setSpacing(0)  # No spacing between message widgets

        # Add original input section if available (inside scroll area)
        original_input_section = self._create_original_input_section(session)
        if original_input_section:
            messages_layout.addWidget(original_input_section)

        # Add message content to container
        if session.messages_to_user:
            for message in session.messages_to_user:
                message_widget = self._create_message_widget(message)
                messages_layout.addWidget(message_widget)

        # Add stretch to push content to top
        messages_layout.addStretch()

        # Set container as scroll area widget
        scroll_area.setWidget(messages_container)
        layout.addWidget(scroll_area)

        # Set styling
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 5px;
            }
        """)

        return widget

    def render_review(self, session: Session) -> QWidget:
        """
        Render a Review-level session (multi-turn conversation).

        Args:
            session: Session to render

        Returns:
            QWidget: Conversation widget with history and input
        """
        logger.debug("Rendering Review conversation")

        # Create main widget
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Add header
        header = self._create_header(session)
        layout.addWidget(header)

        # Add separator (light gray split line)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("""
            QFrame {
                border: none;
                background-color: #e0e0e0;
                max-height: 1px;
            }
        """)
        layout.addWidget(separator)

        # Create scroll area for message content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Create container widget for messages
        messages_container = QWidget()
        messages_layout = QVBoxLayout()
        messages_container.setLayout(messages_layout)
        messages_layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins for alignment
        messages_layout.setSpacing(0)  # No spacing between message widgets

        # Add original input section if available (inside scroll area)
        original_input_section = self._create_original_input_section(session)
        if original_input_section:
            messages_layout.addWidget(original_input_section)

        # Add message content to container
        if session.messages_to_user:
            for message in session.messages_to_user:
                message_widget = self._create_message_widget_for_review(message)
                messages_layout.addWidget(message_widget)

        # Add stretch to push content to top
        messages_layout.addStretch()

        # Set container as scroll area widget
        scroll_area.setWidget(messages_container)
        layout.addWidget(scroll_area)

        # Only add input area if session is not completed
        if session.status != 'completed':
            # Add input area (fixed at bottom)
            input_layout = QHBoxLayout()

            input_field = QLineEdit()
            input_field.setPlaceholderText("Type your message or /finish to end conversation")
            input_field.setMinimumHeight(35)
            # Add deep gray border to input field
            input_field.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #666666;
                    border-radius: 5px;
                    padding: 5px;
                }
            """)

            send_button = QPushButton("Send")
            send_button.setMinimumWidth(80)
            send_button.setMinimumHeight(35)
            # Match Yes button style: light gray background, black text
            send_button.setStyleSheet("""
                QPushButton {
                    background-color: #e8e8e8;
                    color: black;
                    border: none;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
            """)

            input_layout.addWidget(input_field)
            input_layout.addWidget(send_button)

            layout.addLayout(input_layout)

            # Store references for later use
            widget.input_field = input_field
            widget.send_button = send_button

        # Set styling for main widget
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 5px;
            }
        """)

        return widget

    def _create_header(self, session: Session) -> QWidget:
        """
        Create header widget with title and metadata.

        Args:
            session: Session object

        Returns:
            QWidget: Header widget
        """
        header_widget = QWidget()
        main_layout = QVBoxLayout()
        header_widget.setLayout(main_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # Top row: Level badge + Title + Status badge
        top_row = QWidget()
        top_layout = QHBoxLayout()
        top_row.setLayout(top_layout)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Level badge with color coding
        level = session.level
        level_color = self._get_level_color(level)
        level_label = QLabel(f"{level}")
        level_label.setStyleSheet(f"""
            QLabel {{
                background-color: {level_color};
                color: white;
                padding: 3px 8px;
                border-radius: 5px;
                font-weight: bold;
            }}
        """)
        top_layout.addWidget(level_label)

        # Title (from first message or intent)
        title_text = session.title

        title_label = QLabel(title_text)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(False)
        title_label.setFont(title_font)
        top_layout.addWidget(title_label)

        # Spacing
        top_layout.addStretch()

        # Status icon (using custom widget instead of text badge)
        status = session.status
        status_icon = StatusIconWidget(status)
        top_layout.addWidget(status_icon)

        main_layout.addWidget(top_row)

        # Source info (bottom row)
        source = session.metadata.get('source', 'Unknown')
        source_label = QLabel(f"Source: {source}")
        source_label.setStyleSheet("""
            QLabel {
                color: #999;
                font-size: 12px;
                padding-left: 0px;
            }
        """)
        main_layout.addWidget(source_label)

        return header_widget

    def _create_original_input_section(self, session: Session) -> Optional[QWidget]:
        """
        Create original input section to display user's input.

        Args:
            session: Session object

        Returns:
            QWidget: Original input section widget, or None if no input exists
        """
        # Get original input from metadata
        original_input = session.metadata.get('intent_context')

        # Skip if no original input or empty dict
        if not original_input or not isinstance(original_input, dict):
            return None

        input_type = original_input.get('type')
        input_data = original_input.get('data')

        # Skip if no data
        if not input_data:
            return None

        # Create container widget
        section_widget = QWidget()
        layout = QVBoxLayout()
        section_widget.setLayout(layout)
        layout.setContentsMargins(15, 10, 15, 5)  # Left, Top, Right, Bottom - align with Assistant
        layout.setSpacing(8)

        # Create "User" label (bold, larger font, no background)
        user_label = QLabel("User")
        user_font = QFont()
        user_font.setBold(True)
        user_font.setPointSize(14)  # 30% larger (12 * 1.3 ≈ 15.6, rounded to 14)
        user_label.setFont(user_font)
        user_label.setStyleSheet("color: #333; padding-left: 0px;")  # No extra padding
        layout.addWidget(user_label)

        # Display input based on type
        if input_type == 'text':
            # Create text display label
            text_label = QLabel()
            text_label.setText(input_data)
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse |
                Qt.TextSelectableByKeyboard
            )
            text_label.setStyleSheet("""
                QLabel {
                    padding: 0px;
                    padding-left: 0px;
                    color: #333;
                    line-height: 1.5;
                }
            """)
            layout.addWidget(text_label)

        elif input_type == 'image':
            # Display image from Data URL
            image_widget = self._create_image_widget(input_data)
            layout.addWidget(image_widget)

        elif input_type == 'multimodal':
            # Display both text and image
            # input_data is a list: [text, image_url]
            if isinstance(input_data, list) and len(input_data) >= 2:
                text_data, image_url = input_data[0], input_data[1]

                # Display text if present
                if text_data:
                    text_label = QLabel()
                    text_label.setText(text_data)
                    text_label.setWordWrap(True)
                    text_label.setTextInteractionFlags(
                        Qt.TextSelectableByMouse |
                        Qt.TextSelectableByKeyboard
                    )
                    text_label.setStyleSheet("""
                        QLabel {
                            padding: 0px;
                            padding-left: 0px;
                            color: #333;
                            line-height: 1.5;
                        }
                    """)
                    layout.addWidget(text_label)

                # Display image if present
                if image_url:
                    if isinstance(image_url, dict):
                        image_url = image_url["url"]
                    image_widget = self._create_image_widget(image_url)
                    layout.addWidget(image_widget)

        else:
            # Unknown type - skip
            return None

        # Set transparent background for section
        section_widget.setStyleSheet("background-color: transparent;")

        return section_widget

    def _create_message_widget(self, message: Dict[str, Any]) -> QWidget:
        """
        Create widget for a single message.

        Args:
            message: Message object

        Returns:
            QWidget: Message display widget
        """
        msg_widget = QWidget()
        layout = QVBoxLayout()
        msg_widget.setLayout(layout)
        layout.setContentsMargins(15, 5, 15, 10)  # Left, Top, Right, Bottom - align with User
        layout.setSpacing(8)

        # Determine role label and styling
        role = message['role']
        role_label_text = role[0].upper() + role[1:]

        # Add role label (bold, larger font, no background)
        role_label = QLabel(role_label_text)
        role_font = QFont()
        role_font.setBold(True)
        role_font.setPointSize(14)
        role_label.setFont(role_font)
        role_label.setStyleSheet("color: #333; padding-left: 0px;")  # No extra padding
        layout.addWidget(role_label)

        # Format message content
        if role == 'user':
            # For user messages, display plain text without gray background
            if isinstance(message['content'], list):
                for msg in message['content']:
                    if msg['type'] == 'text':
                        text_content = msg['text']
                        break
            else:
                text_content = message['content']

            content_label = QLabel()
            content_label.setText(text_content)
            content_label.setWordWrap(True)
            content_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse |
                Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            content_label.setStyleSheet("""
                QLabel {
                    padding: 0px;
                    color: #333;
                    line-height: 1.5;
                }
            """)
            layout.addWidget(content_label)
        elif role == 'assistant':
            # For assistant messages, use formatted content with gray background
            content_html = self._format_message_content(message['content'])

            # Use QLabel for content display - it auto-sizes correctly
            content_label = QLabel()
            content_label.setText(content_html)
            content_label.setTextFormat(Qt.RichText)
            content_label.setWordWrap(True)

            # Enable text selection
            content_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse |
                Qt.TextSelectableByKeyboard
            )

            content_label.setStyleSheet("""
                QLabel {
                    padding: 10px;
                    background-color: #f8f9fa;
                    border-radius: 5px;
                }
            """)

            layout.addWidget(content_label)

        return msg_widget

    def _create_message_widget_for_review(self, message: Dict[str, Any]) -> QWidget:
        """
        Create widget for a single message in Review mode.

        Handles both user and assistant messages with consistent styling.

        Args:
            message: Message object

        Returns:
            QWidget: Message display widget
        """
        msg_widget = QWidget()
        layout = QVBoxLayout()
        msg_widget.setLayout(layout)
        layout.setContentsMargins(15, 5, 15, 10)  # Left, Top, Right, Bottom
        layout.setSpacing(8)

        # Determine role label and styling
        role = message['role']
        role_label_text = role[0].upper() + role[1:]
        
        # Add role label (bold, larger font)
        role_label = QLabel(role_label_text)
        role_font = QFont()
        role_font.setBold(True)
        role_font.setPointSize(14)  # 30% larger (consistent with other levels)
        role_label.setFont(role_font)
        role_label.setStyleSheet("color: #333; padding-left: 0px;")
        layout.addWidget(role_label)

        # Format message content
        if role == 'user':
            # For user messages, display plain text
            if isinstance(message['content'], list):
                for msg in message['content']:
                    if msg['type'] == 'text':
                        text_content = msg['text']
                        break
            else:
                text_content = message['content']
            
            content_label = QLabel()
            content_label.setText(text_content)
            content_label.setWordWrap(True)
            content_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse |
                Qt.TextSelectableByKeyboard
            )
            content_label.setStyleSheet("""
                QLabel {
                    padding: 0px;
                    color: #333;
                    line-height: 1.5;
                }
            """)
            layout.addWidget(content_label)
        elif role == "assistant":
            # For assistant messages, use formatted content with gray background
            content_html = self._format_message_content(message['content'])

            content_label = QLabel()
            content_label.setText(content_html)
            content_label.setTextFormat(Qt.RichText)
            content_label.setWordWrap(True)

            # Enable text selection
            content_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse |
                Qt.TextSelectableByKeyboard
            )

            content_label.setStyleSheet("""
                QLabel {
                    padding: 10px;
                    background-color: #f8f9fa;
                    border-radius: 5px;
                }
            """)

            layout.addWidget(content_label)

        return msg_widget

    def _format_message_content(self, content: Any) -> str:
        """
        Format message content for display with Markdown support.

        Args:
            content: Message content (dict or string)

        Returns:
            str: HTML-formatted content with Markdown rendered
        """
        if not content:
            return ""

        logger.debug(f'format message content: {content}')

        # [CORRECTED] Initialize mistune with hard_wrap as a keyword argument.
        markdown = mistune.create_markdown(hard_wrap=True)

        # Adjusted CSS for better line spacing and robustness
        markdown_css = """
        <style>
            .markdown-body { 
                line-height: 1.7; /* Increased overall line height */
                word-wrap: break-word; /* Ensure long words/links wrap correctly */
            }
            .markdown-body p {
                margin-top: 0;
                margin-bottom: 0.8em; /* Add vertical space between paragraphs */
            }
            pre { background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; font-family: monospace; }
            code { background-color: #f0f0f0; padding: 2px 4px; border-radius: 2px; font-family: monospace; }
            blockquote { border-left: 3px solid #ccc; padding-left: 10px; margin-left: 0; color: #666; }
            a { color: #007bff; text-decoration: none; }
            a:hover { text-decoration: underline; }
            ul, ol { padding-left: 20px; }
            h1, h2, h3, h4, h5, h6 { margin-top: 15px; margin-bottom: 8px; }
        </style>
        """

        # Helper function to unescape literal escape sequences
        def unescape_text(text: str) -> str:
            """Unescape literal escape sequences like \\n, \\t, etc."""
            if not isinstance(text, str):
                text = str(text)
            text = text.replace('\\n', '\n')
            text = text.replace('\\t', '\t')
            text = text.replace('\\r', '\r')
            return text

        content_html = ''
        wrapper_class = "markdown-body"

        if isinstance(content, dict):
            content_type = content.get('type', 'text')

            if content_type == 'error':
                error_msg = content.get('message', 'An error occurred')
                error_msg = unescape_text(error_msg)
                error_html = markdown(error_msg)
                content_html = f"""
                <div style="color: #dc3545;">
                    <p><strong>Error:</strong></p>
                    <div class="{wrapper_class}">{error_html}</div>
                </div>
                """
            else:
                message = content.get('message', '')
                if message:
                    message = unescape_text(message)
                    message_html = markdown(message)
                    content_html = f'<div class="{wrapper_class}">{message_html}</div>'
                elif 'data' in content:
                    data = content.get('data')
                    data_str = unescape_text(data)
                    data_html = markdown(f'```\n{data_str}\n```')
                    content_html = f'<div class="{wrapper_class}">{data_html}</div>'
                else:
                    content_html = '<div>No content</div>'

        elif isinstance(content, str):
            content = unescape_text(content)
            content_html = markdown(content)
            content_html = f'<div class="{wrapper_class}">{content_html}</div>'

        else:
            # Fallback for other types (int, list, etc.)
            # Render as a safe, escaped code block for clarity.
            text = unescape_text(str(content))
            safe_text = escape(text)
            content_html = markdown(f'```\n{safe_text}\n```')
            content_html = f'<div class="{wrapper_class}">{content_html}</div>'
        
        return f"{markdown_css}{content_html}"

    def _format_conversation_history(self, messages: list) -> str:
        """
        Format conversation history as HTML.

        Args:
            messages: List of Message objects

        Returns:
            str: HTML-formatted conversation
        """
        html_parts = []

        for msg in messages:
            role = msg['role']

            # Role-based styling
            if role == 'user':
                bg_color = '#e3f2fd'
                align = 'right'
                role_name = 'You'
            elif role == 'assistant':
                bg_color = '#f5f5f5'
                align = 'left'
                role_name = 'Assistant'
            # else:
            #     bg_color = '#fff3cd'
            #     align = 'left'
            #     role_name = 'System'

            # Format content
            if isinstance(msg['content'], list):
                for msg in msg['content']:
                    if msg['type'] == 'text':
                        content_text = msg['text']
                        break
            else:
                content_text = msg['content']

            msg_html = f"""
            <div style="text-align: {align}; margin: 5px 0;">
                <div style="display: inline-block; background-color: {bg_color}; padding: 10px; border-radius: 8px; max-width: 70%;">
                    <div style="font-size: 10px; color: #666; margin-bottom: 3px;">
                        <strong>{role_name}</strong>
                    </div>
                    <div>{content_text}</div>
                </div>
            </div>
            """
            html_parts.append(msg_html)

        return ''.join(html_parts)

    def _create_image_widget(self, data_url: str, max_width: int = 200) -> QLabel:
        """
        Create image widget from base64 Data URL.

        Args:
            data_url: Base64 Data URL (format: "data:image/png;base64,...")
            max_width: Maximum width for the image (default: 600px)

        Returns:
            QLabel: Widget containing the image, or error message on failure
        """
        try:
            # Extract base64 part from Data URL
            # Format: "data:image/png;base64,iVBORw0KGgo..."
            if ',' not in data_url:
                raise ValueError("Invalid Data URL format")

            base64_str = data_url.split(',', 1)[1]

            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_str)

            # Load into QPixmap
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_bytes):
                raise ValueError("Failed to load image data")

            # Scale down if image is too large (maintain aspect ratio)
            if pixmap.width() > max_width:
                pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

            # Create QLabel to display the image
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setStyleSheet("""
                QLabel {
                    padding: 0px;
                    background-color: transparent;
                    border: none;
                }
            """)

            logger.debug(f"Image widget created successfully (size: {pixmap.width()}x{pixmap.height()})")
            return image_label

        except Exception as e:
            # On error, return a label with error message
            logger.error(f"Failed to create image widget: {e}")
            error_label = QLabel(f"[Failed to display image: {str(e)}]")
            error_label.setStyleSheet("color: #dc3545; font-style: italic;")
            return error_label

    def _get_level_color(self, level: str) -> str:
        """
        Get color code for interaction level.

        Args:
            level: Interaction level (Notify/Review)

        Returns:
            str: Color code
        """
        colors = {
            'Notify': '#4A90E2',     # Blue
            'Review': '#F5A623'      # Pink
        }
        return colors.get(level, '#4A90E2')

    def _get_status_color(self, status: str) -> str:
        """
        Get color code for status badge.

        Args:
            status: Session status

        Returns:
            str: Color code
        """
        colors = {
            'pending': '#6c757d',    # Gray
            'active': '#007bff',     # Blue
            'completed': '#28a745',  # Green
            'error': '#dc3545'       # Red
        }
        return colors.get(status, '#6c757d')
