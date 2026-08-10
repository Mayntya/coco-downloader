# coding: utf-8
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import CaptionLabel, ComboBox, IndeterminateProgressBar, SearchLineEdit, SimpleCardWidget, setFont


class SearchCard(SimpleCardWidget):
    """Search card with search input and platform selector"""

    searchRequested = pyqtSignal(str, str)
    platformChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(220)

        self.vBoxLayout = QVBoxLayout(self)
        self.titleLabel = QLabel(self.tr("发现你的音乐世界"), self)
        self.descLabel = QLabel(
            self.tr("无论是熟悉的旋律，还是未知的惊喜，都在这里等你探索 ✨"),
            self
        )

        self.searchLayout = QHBoxLayout()
        self.searchInput = SearchLineEdit(self)
        self.platformComboBox = ComboBox(self)
        self.progressBar = IndeterminateProgressBar(self)
        self.previewHintLabel = CaptionLabel(self.tr("当前平台不支持试听，仅支持下载"), self)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        setFont(self.titleLabel, 24, QFont.Weight.Bold)
        setFont(self.descLabel, 14, QFont.Weight.Normal)

        self.titleLabel.setObjectName('titleLabel')
        self.descLabel.setObjectName('descLabel')
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.descLabel.setAlignment(Qt.AlignCenter)

        self.searchInput.setPlaceholderText(self.tr("搜索歌曲、歌手或专辑..."))
        self.searchInput.setFixedHeight(40)
        self.searchInput.searchSignal.connect(self._on_search)

        self.platformComboBox.setFixedWidth(150)
        self.platformComboBox.setFixedHeight(40)
        self.platformComboBox.addItems([
            self.tr("音源1"),
            self.tr("音源2"),
            self.tr("音源3"),
            self.tr("歌曲海"),
            self.tr("波点"),
            self.tr("QQMP3"),
            self.tr("咪咕"),
            self.tr("力音"),
            self.tr("煎饼-1"),
            self.tr("煎饼-2"),
        ])
        self.platformComboBox.setCurrentIndex(0)

        self.searchLayout.setSpacing(12)
        self.searchLayout.addWidget(self.searchInput, 1)
        self.searchLayout.addWidget(self.platformComboBox)

        self.progressBar.hide()
        self.progressBar.pause()
        self.previewHintLabel.hide()
        self.previewHintLabel.setAlignment(Qt.AlignCenter)

        self.vBoxLayout.setContentsMargins(24, 24, 24, 24)
        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.descLabel)
        self.vBoxLayout.addSpacing(8)
        self.vBoxLayout.addLayout(self.searchLayout)
        self.vBoxLayout.addWidget(self.previewHintLabel)
        self.vBoxLayout.addWidget(self.progressBar)

    def _connect_signals(self):
        self.searchInput.returnPressed.connect(self._on_return_pressed)
        self.platformComboBox.currentTextChanged.connect(self._on_platform_changed)

    def _on_search(self, keyword: str):
        """Handle search action"""
        if keyword.strip():
            platform = self.platformComboBox.currentText()
            self.searchRequested.emit(keyword, platform)

    def _on_return_pressed(self) -> None:
        """Search with the same behavior as the search button."""
        self._on_search(self.searchInput.text())

    def clear_search(self):
        """Clear search input"""
        self.searchInput.clear()

    def set_searching(self, searching: bool) -> None:
        """Show or hide the indeterminate search progress bar"""
        self.progressBar.setVisible(searching)
        if searching:
            self.progressBar.resume()
        else:
            self.progressBar.pause()

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable search controls while keeping status widgets active"""
        self.searchInput.setEnabled(enabled)
        self.platformComboBox.setEnabled(enabled)

    def set_preview_hint_visible(self, visible: bool) -> None:
        """Show unsupported-preview hint below the search box"""
        self.previewHintLabel.setVisible(visible)

    def _on_platform_changed(self, platform: str) -> None:
        self.platformChanged.emit(platform)
