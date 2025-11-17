"""
Settings Dialog for Context OS.

Provides UI for managing tool configurations.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox,
    QLineEdit, QGridLayout, QGroupBox, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont
from utils.logger import get_logger
from utils.llm_client import LLMClient
from version import __version__, APP_DISPLAY_NAME

logger = get_logger('SettingsDialog')


class StatusIndicator(QLabel):
    """
    Simple widget that displays a colored text status indicator.

    Red line (-) for disabled, green checkbox (☑) for enabled.
    Clickable to toggle status.
    """

    clicked = pyqtSignal()

    def __init__(self, enabled: bool = False, parent=None):
        super().__init__(parent)
        self._enabled = enabled
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._update_display()

    def set_enabled_status(self, enabled: bool):
        """Update the enabled status and display."""
        self._enabled = enabled
        self._update_display()

    def is_enabled(self) -> bool:
        """Return current enabled status."""
        return self._enabled

    def _update_display(self):
        """Update the text and color based on status."""
        if self._enabled:
            # Green checkbox character (ballot box with check)
            self.setText("☑")
            self.setStyleSheet("""
                color: #28a745;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            """)
        else:
            # Red square character (filled square)
            self.setText("-")
            self.setStyleSheet("""
                color: #dc3545;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            """)

    def mousePressEvent(self, event):
        """Handle mouse click to emit clicked signal."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    """
    Settings dialog for managing Context OS tools and data sources.

    Features:
    - Display all available tools and sources with their status
    - Enable/disable tools and sources with toggle switches
    - Immediate effect (changes applied on toggle)
    - Persists changes to tools.yaml and sources.yaml
    """

    tool_toggled = pyqtSignal(str, bool)      # Signal: (tool_name, enabled)
    adapter_toggled = pyqtSignal(str, bool)   # Signal: (adapter_name, enabled)
    llm_config_updated = pyqtSignal(dict)     # Signal: (new_config)

    def __init__(self, tool_manager, pipeline=None, orchestrator=None, parent=None):
        """
        Initialize the settings dialog.

        Args:
            tool_manager: ToolManager instance
            pipeline: Pipeline instance (optional, for adapter management)
            orchestrator: Orchestrator instance (optional, for LLM config reload)
            parent: Parent widget
        """
        super().__init__(parent)
        self.tool_manager = tool_manager
        self.pipeline = pipeline
        self.orchestrator = orchestrator
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle("Settings - Tools & Data Sources")
        self.setMinimumSize(800, 700)
        self.resize(900, 900)

        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 15, 20, 15)

        # Header
        header_label = QLabel("Settings")
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel("Configure LLM settings, enable or disable tools and data sources for Context OS.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; padding-bottom: 10px;")
        layout.addWidget(desc_label)

        # LLM Configuration Section
        self._add_llm_config_section(layout)

        # User Preferences Section
        self._add_user_preferences_section(layout)

        # Tools Section
        self._add_tools_section(layout)

        # Data Sources Section
        self._add_data_sources_section(layout)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)

        # Footer with version and Close button
        footer_layout = QHBoxLayout()

        # Version text on the left
        version_label = QLabel(f"{APP_DISPLAY_NAME} v{__version__}")
        version_label.setStyleSheet("color: #999; font-size: 11px;")
        footer_layout.addWidget(version_label)

        footer_layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(100)
        apply_btn.clicked.connect(self._on_apply_and_close)
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:pressed {
                background-color: #003D99;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        footer_layout.addWidget(apply_btn)

        layout.addLayout(footer_layout)

        self.setLayout(layout)

    def _add_llm_config_section(self, layout):
        """Add LLM configuration section to the layout."""
        # Create group box for LLM settings
        llm_group = QGroupBox("LLM Configuration")
        llm_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 8px;
                background-color: white;
            }
        """)

        llm_layout = QVBoxLayout()
        llm_layout.setSpacing(8)
        llm_layout.setContentsMargins(10, 5, 10, 10)

        # Grid for input fields (2 rows x 4 columns)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(8)

        input_style = """
            QLineEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QLineEdit:focus {
                border: 1px solid #007AFF;
            }
        """

        # Row 1: Provider and Base URL
        provider_label = QLabel("Provider:")
        provider_label.setStyleSheet("font-weight: normal;")
        self.provider_input = QLineEdit()
        self.provider_input.setPlaceholderText("e.g., openai")
        self.provider_input.setStyleSheet(input_style)
        grid_layout.addWidget(provider_label, 0, 0)
        grid_layout.addWidget(self.provider_input, 0, 1)

        base_url_label = QLabel("Base URL:")
        base_url_label.setStyleSheet("font-weight: normal;")
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("e.g., https://api.openai.com/v1")
        self.base_url_input.setStyleSheet(input_style)
        grid_layout.addWidget(base_url_label, 0, 2)
        grid_layout.addWidget(self.base_url_input, 0, 3)

        # Row 2: Model and API Key
        model_label = QLabel("Model:")
        model_label.setStyleSheet("font-weight: normal;")
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., qwen-flash")
        self.model_input.setStyleSheet(input_style)
        grid_layout.addWidget(model_label, 1, 0)
        grid_layout.addWidget(self.model_input, 1, 1)

        api_key_label = QLabel("API Key:")
        api_key_label.setStyleSheet("font-weight: normal;")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your API key")
        self.api_key_input.setStyleSheet(input_style)
        grid_layout.addWidget(api_key_label, 1, 2)
        grid_layout.addWidget(self.api_key_input, 1, 3)

        # Set column stretch to make inputs expand equally
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(3, 1)

        llm_layout.addLayout(grid_layout)

        llm_group.setLayout(llm_layout)
        layout.addWidget(llm_group)

    def _add_user_preferences_section(self, layout):
        """Add User Preferences section to the layout."""
        # Create group box for User Preferences
        prefs_group = QGroupBox("User Preferences")
        prefs_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 8px;
                background-color: white;
            }
        """)

        prefs_layout = QVBoxLayout()
        prefs_layout.setSpacing(8)
        prefs_layout.setContentsMargins(10, 5, 10, 10)

        # Grid for preferences
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(8)

        # Default Language dropdown
        language_label = QLabel("Preferred Language for LLM:")
        language_label.setStyleSheet("font-weight: normal;")

        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "English",
            "Chinese",
            "Spanish",
            "French",
            "German"
        ])
        self.language_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-width: 200px;
            }
            QComboBox:focus {
                border: 1px solid #007AFF;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666;
                margin-right: 5px;
            }
        """)
        self.language_combo.currentTextChanged.connect(self._on_language_changed)

        grid_layout.addWidget(language_label, 0, 0)
        grid_layout.addWidget(self.language_combo, 0, 1)

        prefs_layout.addLayout(grid_layout)

        prefs_group.setLayout(prefs_layout)
        layout.addWidget(prefs_group)

    def _add_tools_section(self, layout):
        """Add Tools section with table to the layout."""
        # Create group box for Tools
        tools_group = QGroupBox("Tools")
        tools_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 8px;
                background-color: white;
            }
        """)

        tools_layout = QVBoxLayout()
        tools_layout.setSpacing(0)
        tools_layout.setContentsMargins(8, 5, 8, 8)

        # Create tools table
        self.tools_table = QTableWidget()
        self.tools_table.setColumnCount(4)
        self.tools_table.setHorizontalHeaderLabels(["Name", "Type", "Enabled", "Description"])

        # Configure table
        self.tools_table.setSelectionMode(QTableWidget.NoSelection)
        self.tools_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tools_table.verticalHeader().setVisible(False)

        # Set default row height for all rows
        self.tools_table.verticalHeader().setDefaultSectionSize(35)

        # Set column widths
        header = self.tools_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        # Style the table
        self.tools_table.setAlternatingRowColors(True)
        self.tools_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #ddd;
                font-weight: bold;
            }
        """)

        tools_layout.addWidget(self.tools_table)
        tools_group.setLayout(tools_layout)
        layout.addWidget(tools_group)

    def _add_data_sources_section(self, layout):
        """Add Data Sources section with table to the layout."""
        # Create group box for Data Sources
        sources_group = QGroupBox("Data Sources")
        sources_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 8px;
                background-color: white;
            }
        """)

        sources_layout = QVBoxLayout()
        sources_layout.setSpacing(0)
        sources_layout.setContentsMargins(8, 5, 8, 8)

        # Create data sources table
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(4)
        self.sources_table.setHorizontalHeaderLabels(["Name", "Type", "Enabled", "Description"])

        # Configure table
        self.sources_table.setSelectionMode(QTableWidget.NoSelection)
        self.sources_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sources_table.verticalHeader().setVisible(False)

        # Set default row height for all rows
        self.sources_table.verticalHeader().setDefaultSectionSize(35)

        # Set column widths
        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        # Style the table
        self.sources_table.setAlternatingRowColors(True)
        self.sources_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #ddd;
                font-weight: bold;
            }
        """)

        sources_layout.addWidget(self.sources_table)
        sources_group.setLayout(sources_layout)
        layout.addWidget(sources_group)


    def _load_settings(self):
        """Load tools, adapters, and LLM config from managers and populate the UI."""
        # Load LLM configuration
        self._load_llm_config()

        # Load user preferences
        self._load_user_preferences()

        # Get tools status
        tools_status = self.tool_manager.get_all_tools_status()

        # Get adapters status if pipeline is available
        adapters_status = []
        if self.pipeline:
            adapters_status = self.pipeline.get_all_adapters_status()

        # Populate Tools table
        self.tools_table.setRowCount(len(tools_status))
        for row, tool_info in enumerate(tools_status):
            self._add_item_row(self.tools_table, row, tool_info, 'tool')

        # Populate Data Sources table
        self.sources_table.setRowCount(len(adapters_status))
        for row, adapter_info in enumerate(adapters_status):
            self._add_item_row(self.sources_table, row, adapter_info, 'adapter')

        # Update status label
        tools_enabled = sum(1 for t in tools_status if t['enabled'])
        tools_total = len(tools_status)
        adapters_enabled = sum(1 for a in adapters_status if a['enabled'])
        adapters_total = len(adapters_status)

        status_parts = []
        if tools_total > 0:
            status_parts.append(f"{tools_enabled} of {tools_total} tools enabled")
        if adapters_total > 0:
            status_parts.append(f"{adapters_enabled} of {adapters_total} sources enabled")

        self.status_label.setText(", ".join(status_parts) if status_parts else "No items configured")

        logger.info(f"Loaded {tools_total} tools and {adapters_total} adapters in settings dialog")

    def _add_item_row(self, table: QTableWidget, row: int, item_info: dict, item_type: str):
        """
        Add an item (tool or adapter) row to the table.

        Args:
            table: The table to add the row to
            row: Row index
            item_info: Item information dictionary
            item_type: 'tool' or 'adapter'
        """
        # Name
        name_item = QTableWidgetItem(item_info['name'])
        name_item.setFlags(Qt.ItemIsEnabled)
        table.setItem(row, 0, name_item)

        # Type
        type_item = QTableWidgetItem(item_info['type'])
        type_item.setFlags(Qt.ItemIsEnabled)
        table.setItem(row, 1, type_item)

        # Status indicator (red/green circle)
        indicator = StatusIndicator(enabled=item_info['enabled'])

        # Connect indicator to appropriate toggle handler
        if item_type == 'tool':
            indicator.clicked.connect(
                lambda name=item_info['name'], ind=indicator: self._on_indicator_clicked(name, ind, 'tool')
            )
        else:  # adapter
            indicator.clicked.connect(
                lambda name=item_info['name'], ind=indicator: self._on_indicator_clicked(name, ind, 'adapter')
            )

        table.setCellWidget(row, 2, indicator)

        # Description
        desc_item = QTableWidgetItem(item_info['description'])
        desc_item.setFlags(Qt.ItemIsEnabled)
        table.setItem(row, 3, desc_item)

    def _on_indicator_clicked(self, name: str, indicator: StatusIndicator, item_type: str):
        """
        Handle indicator click to toggle status.

        Args:
            name: Name of the item (tool or adapter)
            indicator: The StatusIndicator widget
            item_type: 'tool' or 'adapter'
        """
        # Toggle the status
        new_status = not indicator.is_enabled()

        # Call appropriate toggle handler
        if item_type == 'tool':
            self._on_tool_toggled(name, new_status, indicator)
        else:  # adapter
            self._on_adapter_toggled(name, new_status, indicator)

    def _on_tool_toggled(self, tool_name: str, enabled: bool, indicator: StatusIndicator = None):
        """
        Handle tool toggle event.

        Args:
            tool_name: Name of the tool
            enabled: New enabled status
            indicator: Optional StatusIndicator widget to update
        """
        logger.info(f"Tool toggle requested: {tool_name} -> {enabled}")

        try:
            # Update tool status in ToolManager
            if enabled:
                success = self.tool_manager.enable_tool(tool_name)
            else:
                success = self.tool_manager.disable_tool(tool_name)

            if success:
                # Update indicator visual state
                if indicator:
                    indicator.set_enabled_status(enabled)

                # Update status label with both tools and adapters
                status_text = "enabled" if enabled else "disabled"
                self._update_status_label(f"✓ Tool '{tool_name}' {status_text}")

                # Emit signal
                self.tool_toggled.emit(tool_name, enabled)

                logger.info(f"Tool {tool_name} {status_text} successfully")
            else:
                # Show error
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to {'enable' if enabled else 'disable'} tool '{tool_name}'.\n"
                    f"Check the logs for details."
                )

                # Revert by reloading settings
                self._reload_settings()

        except Exception as e:
            logger.error(f"Error toggling tool {tool_name}: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while updating tool '{tool_name}':\n{str(e)}"
            )
            # Revert by reloading settings
            self._reload_settings()

    def _on_adapter_toggled(self, adapter_name: str, enabled: bool, indicator: StatusIndicator = None):
        """
        Handle adapter toggle event.

        Args:
            adapter_name: Name of the adapter
            enabled: New enabled status
            indicator: Optional StatusIndicator widget to update
        """
        if not self.pipeline:
            logger.error("Pipeline not available, cannot toggle adapter")
            QMessageBox.warning(
                self,
                "Error",
                "Pipeline not available. Cannot toggle data sources."
            )
            self._reload_settings()
            return

        logger.info(f"Adapter toggle requested: {adapter_name} -> {enabled}")

        try:
            # Update adapter status in Pipeline
            if enabled:
                success = self.pipeline.enable_adapter(adapter_name)
            else:
                success = self.pipeline.disable_adapter(adapter_name)

            if success:
                # Update indicator visual state
                if indicator:
                    indicator.set_enabled_status(enabled)

                # Update status label
                status_text = "enabled" if enabled else "disabled"
                self._update_status_label(f"✓ Source '{adapter_name}' {status_text}")

                # Emit signal
                self.adapter_toggled.emit(adapter_name, enabled)

                logger.info(f"Adapter {adapter_name} {status_text} successfully")
            else:
                # Show error
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to {'enable' if enabled else 'disable'} source '{adapter_name}'.\n"
                    f"Check the logs for details."
                )

                # Revert by reloading settings
                self._reload_settings()

        except Exception as e:
            logger.error(f"Error toggling adapter {adapter_name}: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while updating source '{adapter_name}':\n{str(e)}"
            )
            # Revert by reloading settings
            self._reload_settings()

    def _update_status_label(self, message: str = ""):
        """
        Update the status label with current counts and optional message.

        Args:
            message: Optional message to append (e.g., "✓ Tool 'calculator' enabled")
        """
        # Get current status counts
        tools_status = self.tool_manager.get_all_tools_status()
        tools_enabled = sum(1 for t in tools_status if t['enabled'])
        tools_total = len(tools_status)

        adapters_enabled = 0
        adapters_total = 0
        if self.pipeline:
            adapters_status = self.pipeline.get_all_adapters_status()
            adapters_enabled = sum(1 for a in adapters_status if a['enabled'])
            adapters_total = len(adapters_status)

        # Build status text
        status_parts = []
        if tools_total > 0:
            status_parts.append(f"{tools_enabled} of {tools_total} tools enabled")
        if adapters_total > 0:
            status_parts.append(f"{adapters_enabled} of {adapters_total} sources enabled")

        status_text = ", ".join(status_parts) if status_parts else "No items configured"

        # Add message if provided
        if message:
            status_text += f" | {message}"

        self.status_label.setText(status_text)

    def _reload_settings(self):
        """Reload the settings table (used after errors to reset state)."""
        self._load_settings()

    def refresh(self):
        """Refresh the settings list (can be called externally)."""
        self._load_settings()

    def _load_llm_config(self):
        """Load current LLM configuration from Pipeline and populate input fields."""
        if not self.pipeline:
            logger.warning("Pipeline not available, cannot load LLM config")
            return

        try:
            engine_config = self.pipeline.get_engine_config()

            # Populate input fields
            self.provider_input.setText(engine_config.get('llm_provider', ''))
            self.model_input.setText(engine_config.get('llm_model', ''))
            self.base_url_input.setText(engine_config.get('llm_base_url', ''))
            self.api_key_input.setText(engine_config.get('llm_api_key', ''))

            logger.info("LLM configuration loaded into settings dialog")

        except Exception as e:
            logger.error(f"Error loading LLM config: {e}")

    def _load_user_preferences(self):
        """Load current user preferences from Pipeline and populate UI."""
        if not self.pipeline:
            logger.warning("Pipeline not available, cannot load user preferences")
            return

        try:
            user_config = self.pipeline.get_user_config()
            default_language = user_config.get('default_language', 'Chinese')

            # Set the combo box to the current language
            index = self.language_combo.findText(default_language)
            if index >= 0:
                # Temporarily disconnect signal to avoid triggering update during load
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentIndex(index)
                self.language_combo.blockSignals(False)
            else:
                logger.warning(f"Default language '{default_language}' not found in dropdown, defaulting to Chinese")
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentText('Chinese')
                self.language_combo.blockSignals(False)

            logger.info(f"User preferences loaded: default_language={default_language}")

        except Exception as e:
            logger.error(f"Error loading user preferences: {e}")

    def _on_language_changed(self, new_language: str):
        """
        Handle language dropdown change event.

        Updates both system.yaml (user.default_language) and tools.yaml (translator.target_lang).

        Args:
            new_language: The newly selected language
        """
        if not new_language:
            return

        if not self.pipeline:
            logger.error("Pipeline not available, cannot update language")
            QMessageBox.warning(
                self,
                "Error",
                "Pipeline not available. Cannot update default language."
            )
            return

        logger.info(f"Language changed to: {new_language}")

        try:
            # Step 1: Update system.yaml user.default_language
            if not self.pipeline.update_user_config('default_language', new_language):
                raise Exception("Failed to update system.yaml")

            # Step 2: Sync to translator tool's target_lang
            if not self.pipeline.sync_language_to_translator(new_language):
                raise Exception("Failed to sync language to translator tool")

            # Step 3: Reload user config in Detector and ReactAgent
            if not self.pipeline.reload_user_config():
                raise Exception("Failed to reload user config in engine components")

            # Update status label with success message
            self._update_status_label(f"✓ Default language changed to '{new_language}'")

            logger.info(f"✓ Default language successfully updated to: {new_language}")

        except Exception as e:
            logger.error(f"Error updating language: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to update default language:\n{str(e)}\n\nPlease check the logs for details."
            )
            # Reload settings to reset UI to actual state
            self._reload_settings()

    def _on_apply_and_close(self):
        """Handle Apply button click - validate LLM config if changed, then close."""
        # Check if LLM config has changed
        if self._has_llm_config_changed():
            # Get new config from inputs
            new_config = self._get_llm_config_from_inputs()

            # Show validating status
            self.status_label.setText("⏳ Validating LLM configuration...")
            self.status_label.setStyleSheet("color: #007AFF; font-size: 11px;")

            # Disable Apply button during validation
            sender_btn = self.sender()
            if sender_btn:
                sender_btn.setEnabled(False)

            # Create and start validation thread
            self.validation_thread = ValidationThread(new_config)
            self.validation_thread.validation_complete.connect(
                lambda success, message, config: self._on_validation_complete_and_close(
                    success, message, config, sender_btn
                )
            )
            self.validation_thread.start()
        else:
            # No LLM config change, close directly
            self.accept()

    def _has_llm_config_changed(self) -> bool:
        """Check if LLM configuration has been modified."""
        if not self.pipeline:
            return False

        current_config = self.pipeline.get_engine_config()

        return (
            self.provider_input.text().strip() != current_config.get('llm_provider', '') or
            self.model_input.text().strip() != current_config.get('llm_model', '') or
            self.base_url_input.text().strip() != current_config.get('llm_base_url', '') or
            self.api_key_input.text().strip() != current_config.get('llm_api_key', '')
        )

    def _get_llm_config_from_inputs(self) -> dict:
        """Get LLM configuration from input fields."""
        # Get current engine config to preserve other settings
        current_config = {}
        if self.pipeline:
            current_config = self.pipeline.get_engine_config()

        # Update with new values from inputs
        current_config['llm_provider'] = self.provider_input.text().strip()
        current_config['llm_model'] = self.model_input.text().strip()
        current_config['llm_base_url'] = self.base_url_input.text().strip()
        current_config['llm_api_key'] = self.api_key_input.text().strip()

        return current_config

    def _on_validation_complete_and_close(self, success: bool, message: str, config: dict, button):
        """Handle validation completion and close dialog if successful."""
        # Re-enable button
        if button:
            button.setEnabled(True)

        if success:
            # Apply configuration
            if self._apply_llm_config(config):
                logger.info("LLM configuration updated successfully")
                # Close dialog on success
                self.accept()
            else:
                # Show error if apply failed
                self.status_label.setText("")
                QMessageBox.warning(
                    self,
                    "Error",
                    "Failed to apply LLM configuration. Check logs for details."
                )
        else:
            # Validation failed - show error dialog
            self.status_label.setText("")
            QMessageBox.warning(
                self,
                "Validation Failed",
                f"LLM configuration validation failed:\n\n{message}\n\nPlease check your settings and try again."
            )
            logger.warning(f"LLM config validation failed: {message}")

    def _apply_llm_config(self, config: dict) -> bool:
        """Apply LLM configuration by reloading Pipeline engine components."""
        if not self.pipeline:
            logger.error("Pipeline not available, cannot apply LLM config")
            return False

        try:
            # Reload engine configuration in Pipeline
            success = self.pipeline.reload_engine_config(config)

            if success and self.orchestrator:
                # Update Handler's component references
                self.orchestrator.update_handler_components()

            if success:
                # Emit signal
                self.llm_config_updated.emit(config)

            return success

        except Exception as e:
            logger.error(f"Error applying LLM config: {e}")
            return False


class ValidationThread(QThread):
    """Thread for validating LLM configuration without blocking UI."""

    validation_complete = pyqtSignal(bool, str, dict)  # (success, message, config)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        """Run validation in background thread."""
        try:
            success, message = LLMClient.validate_config(self.config, timeout=5)
            self.validation_complete.emit(success, message, self.config)
        except Exception as e:
            self.validation_complete.emit(False, f"Validation error: {str(e)}", self.config)
