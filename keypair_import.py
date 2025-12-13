import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QFileDialog, QMessageBox,
                             QLineEdit, QTabWidget, QGroupBox)
from PyQt6.QtCore import pyqtSignal
from solders.keypair import Keypair


class KeypairImportWidget(QWidget):
    """Widget for importing Solana keypairs with multiple methods"""

    keypair_imported = pyqtSignal(Keypair)  # Signal emitted when keypair is successfully imported

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_keypair = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Title
        title = QLabel("Import Wallet Keypair")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        # Tab widget for different import methods
        self.tabs = QTabWidget()

        # Tab 1: Private Key (Base58)
        self.tabs.addTab(self.create_base58_tab(), "Private Key")

        # Tab 2: JSON File (Phantom/Solflare format)
        self.tabs.addTab(self.create_json_tab(), "JSON File")

        # Tab 3: Byte Array
        self.tabs.addTab(self.create_byte_array_tab(), "Byte Array")

        layout.addWidget(self.tabs)

        # Current wallet info
        self.wallet_info_group = QGroupBox("Current Wallet")
        wallet_layout = QVBoxLayout()

        self.pubkey_label = QLabel("Public Key: None")
        self.pubkey_label.setWordWrap(True)
        self.pubkey_label.setStyleSheet("font-family: monospace; padding: 5px;")
        wallet_layout.addWidget(self.pubkey_label)

        # Clear wallet button
        clear_btn = QPushButton("Clear Wallet")
        clear_btn.clicked.connect(self.clear_wallet)
        clear_btn.setMaximumWidth(200)
        wallet_layout.addWidget(clear_btn)

        self.wallet_info_group.setLayout(wallet_layout)
        layout.addWidget(self.wallet_info_group)

        self.setLayout(layout)

    def create_base58_tab(self):
        """Create tab for Base58 private key import"""
        widget = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Enter your private key (Base58 encoded):")
        layout.addWidget(label)

        self.base58_input = QTextEdit()
        self.base58_input.setPlaceholderText("Example: 5Jv8W...")
        self.base58_input.setMaximumHeight(80)
        layout.addWidget(self.base58_input)

        import_btn = QPushButton("Import Private Key")
        import_btn.clicked.connect(self.import_from_base58)
        import_btn.setMaximumWidth(200)
        layout.addWidget(import_btn)

        # Warning message
        warning = QLabel("⚠️ Never share your private key with anyone!")
        warning.setStyleSheet("color: #ff6b6b; font-weight: bold; margin-top: 10px;")
        layout.addWidget(warning)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_json_tab(self):
        """Create tab for JSON file import (Phantom/Solflare format)"""
        widget = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Import wallet from JSON file:")
        layout.addWidget(label)

        # File path display
        self.json_path_label = QLabel("No file selected")
        self.json_path_label.setStyleSheet("padding: 5px; background-color: #f0f0f0; border-radius: 3px;color: #000000")
        self.json_path_label.setMaximumWidth(300)
        layout.addWidget(self.json_path_label)

        # Buttons

        select_btn = QPushButton("Select JSON File")
        select_btn.clicked.connect(self.select_json_file)
        select_btn.setMaximumWidth(200)

        import_btn = QPushButton("Import from JSON")
        import_btn.clicked.connect(self.import_from_json)
        import_btn.setMaximumWidth(200)

        layout.addWidget(select_btn)
        layout.addWidget(import_btn)

        # Info
        info = QLabel("Supports Phantom and Solflare wallet export formats")
        info.setStyleSheet("color: #9c9898; font-size: 11px; margin-top: 10px;")
        layout.addWidget(info)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_byte_array_tab(self):
        """Create tab for byte array import"""
        widget = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Enter byte array (comma-separated or JSON array):")
        layout.addWidget(label)

        self.byte_array_input = QTextEdit()
        self.byte_array_input.setPlaceholderText("[1,2,3,...] or 1,2,3,...")
        self.byte_array_input.setMaximumHeight(100)
        layout.addWidget(self.byte_array_input)

        import_btn = QPushButton("Import Byte Array")
        import_btn.clicked.connect(self.import_from_byte_array)
        import_btn.setMaximumWidth(200)
        layout.addWidget(import_btn)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def import_from_base58(self):
        """Import keypair from Base58 encoded private key"""
        private_key = self.base58_input.toPlainText().strip()

        if not private_key:
            QMessageBox.warning(self, "Error", "Please enter a private key")
            return

        try:
            keypair = Keypair.from_base58_string(private_key)
            self.set_keypair(keypair)
            QMessageBox.information(self, "Success", "Keypair imported successfully!")
            self.base58_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import keypair:\n{str(e)}")

    def select_json_file(self):
        """Open file dialog to select JSON file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Keypair JSON File",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            self.json_path_label.setText(file_path)

    def import_from_json(self):
        """Import keypair from JSON file"""
        file_path = self.json_path_label.text()

        if file_path == "No file selected":
            QMessageBox.warning(self, "Error", "Please select a JSON file first")
            return

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Handle different JSON formats
            if isinstance(data, list):
                # Direct byte array format [1, 2, 3, ...]
                byte_array = bytes(data)
            elif isinstance(data, dict):
                # Check for common key names
                if 'secretKey' in data:
                    byte_array = bytes(data['secretKey'])
                elif 'privateKey' in data:
                    byte_array = bytes(data['privateKey'])
                else:
                    raise ValueError("JSON format not recognized. Expected 'secretKey' or 'privateKey' field")
            else:
                raise ValueError("Invalid JSON format")

            keypair = Keypair.from_bytes(byte_array)
            self.set_keypair(keypair)
            QMessageBox.information(self, "Success", "Keypair imported from JSON successfully!")
            self.json_path_label.setText("No file selected")

        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "File not found")
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "Invalid JSON file")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import keypair:\n{str(e)}")

    def import_from_byte_array(self):
        """Import keypair from byte array"""
        byte_string = self.byte_array_input.toPlainText().strip()

        if not byte_string:
            QMessageBox.warning(self, "Error", "Please enter a byte array")
            return

        try:
            # Try to parse as JSON first
            if byte_string.startswith('['):
                byte_list = json.loads(byte_string)
            else:
                # Parse comma-separated values
                byte_list = [int(x.strip()) for x in byte_string.split(',')]

            byte_array = bytes(byte_list)
            keypair = Keypair.from_bytes(byte_array)
            self.set_keypair(keypair)
            QMessageBox.information(self, "Success", "Keypair imported from byte array successfully!")
            self.byte_array_input.clear()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import keypair:\n{str(e)}")

    def set_keypair(self, keypair: Keypair):
        """Set the current keypair and update UI"""
        self.current_keypair = keypair
        pubkey = str(keypair.pubkey())
        self.pubkey_label.setText(f"Public Key: {pubkey}")
        self.keypair_imported.emit(keypair)

    def clear_wallet(self):
        """Clear the current wallet"""
        reply = QMessageBox.question(
            self,
            "Clear Wallet",
            "Are you sure you want to clear the current wallet?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.keypair_imported.emit(self.current_keypair)
            self.current_keypair = None
            self.pubkey_label.setText("Public Key: None")
            QMessageBox.information(self, "Cleared", "Wallet cleared successfully")


    def get_keypair(self):
        """Get the current keypair"""
        return self.current_keypair

    def get_public_key(self):
        """Get the current public key as string"""
        if self.current_keypair:
            return str(self.current_keypair.pubkey())
        return None

    def get_private_key(self):
        """Get the current private key as Base58 string"""
        if self.current_keypair:
            return str(self.current_keypair)
        return None


# Example usage in your main application
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    widget = KeypairImportWidget()


    # Connect signal to handle imported keypair
    def on_keypair_imported(keypair):
        print(f"Keypair imported! Public key: {keypair.pubkey()}")


    widget.keypair_imported.connect(on_keypair_imported)
    widget.show()

    sys.exit(app.exec())
