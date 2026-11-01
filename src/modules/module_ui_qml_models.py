"""Qt models and image providers used by the QML controller."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class ConversationModel(QAbstractListModel):
    SpeakerRole = Qt.UserRole + 1
    MessageRole = Qt.UserRole + 2
    TimeRole = Qt.UserRole + 3
    IsTarsRole = Qt.UserRole + 4

    def __init__(self, maximum_rows: int = 40, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._items: list[dict[str, object]] = []
        self._maximum_rows = maximum_rows

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        key = {
            self.SpeakerRole: "speaker",
            self.MessageRole: "message",
            self.TimeRole: "time",
            self.IsTarsRole: "isTars",
        }.get(role)
        return self._items[index.row()].get(key) if key else None

    def roleNames(self) -> dict[int, bytes]:  # noqa: N802
        return {
            self.SpeakerRole: b"speaker",
            self.MessageRole: b"message",
            self.TimeRole: b"messageTime",
            self.IsTarsRole: b"isTars",
        }

    def add_message(self, speaker: str, message: str, is_tars: bool) -> None:
        if len(self._items) >= self._maximum_rows:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._items.pop(0)
            self.endRemoveRows()
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append({
            "speaker": speaker,
            "message": message,
            "time": datetime.now().strftime("%I:%M %p").lstrip("0"),
            "isTars": is_tars,
        })
        self.endInsertRows()

    def update_last_message(self, message: str) -> None:
        if not self._items:
            self.add_message("TARS", message, True)
            return
        row = len(self._items) - 1
        self._items[row]["message"] = message
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.MessageRole])

    def update_speaker(self, old_speaker: str, text: str, new_speaker: str) -> None:
        for row in range(len(self._items) - 1, -1, -1):
            item = self._items[row]
            if item["speaker"] == old_speaker and item["message"] == text:
                item["speaker"] = new_speaker
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.SpeakerRole])
                return


class CameraImageProvider(QQuickImageProvider):
    def __init__(self, controller) -> None:  # noqa: ANN001
        super().__init__(QQuickImageProvider.Image)
        self._controller = controller

    def requestImage(self, _image_id, size, requested_size):  # noqa: N802, ANN001
        image = self._controller.camera_image()
        if image.isNull():
            image = QImage(640, 480, QImage.Format_RGB888)
            image.fill(Qt.black)
        if requested_size.isValid():
            image = image.scaled(
                requested_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
