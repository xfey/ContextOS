"""
Notification Manager for Context OS (macOS Native Version).

Manages system notifications using PyObjC and the UserNotifications framework.
"""

import uuid
from typing import Optional, Callable

from Foundation import NSObject
from UserNotifications import (
    UNUserNotificationCenter,
    UNMutableNotificationContent,
    UNNotificationRequest,
    UNAuthorizationOptionAlert,
    UNAuthorizationOptionSound,
    UNNotificationDefaultActionIdentifier
)
from AppKit import NSSound
from models.session import Session
from utils.logger import get_logger

logger = get_logger('NotificationManager')


class NotificationDelegate(NSObject):
    """
    Delegate for handling user interactions with notifications.

    This object will be registered with the UNUserNotificationCenter and follows
    the standard macOS Delegate Pattern for handling notification callbacks.
    """

    def initWithCallback_(self, callback: Callable[[str], None]):
        """
        Custom initializer to store the click callback.

        Args:
            callback: Python function to call when notification is clicked

        Returns:
            self: Initialized delegate instance
        """
        self = self.init()
        if self is None:
            return None

        self.on_notification_clicked_callback = callback
        return self

    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
        self, center, response, completionHandler
    ):
        """
        Called when a user interacts with a notification.

        This is the standard macOS callback method for notification interactions.

        Args:
            center: UNUserNotificationCenter instance
            response: UNNotificationResponse containing user action and notification data
            completionHandler: Block to call when done processing
        """
        # Check if user clicked the notification itself (not a button)
        if response.actionIdentifier() == UNNotificationDefaultActionIdentifier:

            # Safely extract session_id from notification's userInfo dictionary
            user_info = response.notification().request().content().userInfo()
            session_id = user_info.get('session_id')

            if session_id:
                logger.info(f"Notification clicked for session: {session_id}")
                if self.on_notification_clicked_callback:
                    try:
                        # Call the callback function passed from NotificationManager
                        self.on_notification_clicked_callback(session_id)
                        logger.debug(f"Session {session_id} opened via notification click")
                    except Exception as e:
                        logger.error(f"Error handling notification click: {e}", exc_info=True)
                else:
                    logger.warning("No notification click handler registered in delegate")
            else:
                logger.warning("Notification clicked but no session_id found in userInfo")

        # Must call completionHandler to notify system we're done processing
        completionHandler()


class NotificationManager:
    """
    NotificationManager handles system notifications using the native macOS framework.

    Uses PyObjC to interact with UNUserNotificationCenter for a fully native
    notification experience on macOS.

    Features:
    - 100% native macOS look and feel
    - Robust click handling by embedding session_id in notification metadata
    - Asks for user permission on first use
    - Uses the main application icon automatically
    - Thread-safe notification delivery
    """

    def __init__(self, on_notification_clicked: Optional[Callable[[str], None]] = None):
        """
        Initialize the NotificationManager.

        Args:
            on_notification_clicked: Optional callback function(session_id) called when notification is clicked
        """
        self.center = UNUserNotificationCenter.currentNotificationCenter()

        # Create and set delegate
        # This delegate object will handle all notification interactions
        self.delegate = NotificationDelegate.alloc().initWithCallback_(on_notification_clicked)
        self.center.setDelegate_(self.delegate)

        logger.info("Native NotificationManager initialized and delegate set")

    def request_authorization(self):
        """
        Request user permission to show notifications.

        This should be called once when the application starts.
        On macOS 10.14+, apps must explicitly request notification permission.
        If already granted/denied, this won't show another prompt.
        """
        options = UNAuthorizationOptionAlert | UNAuthorizationOptionSound

        def completion_handler(granted, error):
            if error:
                logger.error(f"Error requesting notification authorization: {error}")
            elif granted:
                logger.info("Notification authorization granted")
            else:
                logger.warning("Notification authorization denied by user")

        self.center.requestAuthorizationWithOptions_completionHandler_(options, completion_handler)

    def show_notification(self, session: Session):
        """
        Show a system notification for a new session.

        Displays a native macOS notification with:
        - Title: The session title
        - Message: The message content from the first assistant message (truncated if needed)
        - Icon: App's .icns icon (automatically used by macOS)

        When user clicks the notification, the session will be opened in Inbox.

        Args:
            session: Session object to notify about
        """
        try:
            session_id = session.metadata.get('uuid')
            if not session_id:
                logger.error("Cannot show notification for session with no UUID")
                return

            # 1. Create notification content
            content = UNMutableNotificationContent.alloc().init()
            content.setTitle_(session.title)
            content.setBody_(self._get_notification_message(session))
            content.setSound_(NSSound.soundNamed_("Default"))

            # 2. Embed session_id into userInfo
            # This is the key to reliable click callback handling!
            user_info = {"session_id": session_id}
            content.setUserInfo_(user_info)

            # 3. Create notification request
            # Use UUID to ensure each request is unique
            identifier = str(uuid.uuid4())
            # trigger=None means send immediately
            request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
                identifier, content, None
            )

            # 4. Add request to notification center for delivery
            self.center.addNotificationRequest_withCompletionHandler_(request, None)

            logger.debug(f"Native notification queued for session: {session_id}")

        except Exception as e:
            logger.error(f"Error showing native notification: {e}", exc_info=True)

    def _get_notification_message(self, session: Session) -> str:
        """
        Extract notification message content from session's first message.

        Gets the message field from the first assistant message.
        Falls back to generic message if not found.
        Truncates long messages to fit notification constraints.

        Args:
            session: Session object

        Returns:
            str: Notification message content (truncated if needed)
        """
        # Default fallback message
        default_message = "New session created"

        # Check if session has messages
        if not session.messages_to_user or len(session.messages_to_user) == 0:
            logger.debug("Session has no messages_to_user, using default message")
            return default_message

        # Find first assistant message
        for msg in session.messages_to_user:
            if msg.get('role') == "assistant" and msg.get('content'):
                content = msg['content']
                max_length = 100
                if len(content) > max_length:
                    return content[:max_length - 3] + "..."
                return content

        # No assistant message found
        logger.debug("No assistant message found in session")
        return default_message
