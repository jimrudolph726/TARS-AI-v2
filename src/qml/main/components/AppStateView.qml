import QtQuick
import QtQuick.Controls
import "UiTokens.js" as Ui

Item {
    id: root

    // Supported states: content, loading, error, empty, disabled.
    property string state: "content"
    property string title: state === "loading" ? "LOADING"
        : state === "error" ? "UNAVAILABLE"
        : state === "empty" ? "NOTHING TO SHOW"
        : state === "disabled" ? "DISABLED"
        : ""
    property string detail: ""
    property string iconText: state === "loading" ? "..."
        : state === "error" ? "!"
        : state === "empty" ? "--"
        : state === "disabled" ? "OFF"
        : ""
    property color accent: state === "error" ? "#ff3852"
        : state === "loading" ? "#ffc857"
        : "#829199"
    property real uiScale: 1.0

    visible: state !== "content"

    Column {
        anchors.centerIn: parent
        width: Math.max(0, parent.width - 2 * Ui.spaceXl * root.uiScale)
        spacing: Ui.spaceMd * root.uiScale

        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.state === "loading"
            running: visible
            width: 32 * root.uiScale
            height: width
        }
        Text {
            visible: root.state !== "loading" && root.iconText.length > 0
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.iconText
            color: root.accent
            font.family: displayFontFamily
            font.pixelSize: 22 * root.uiScale
            font.bold: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.title
            color: root.accent
            font.family: displayFontFamily
            font.pixelSize: Math.max(Ui.textBody, 11 * root.uiScale)
            font.bold: true
            font.letterSpacing: 1.1 * root.uiScale
        }
        Text {
            visible: root.detail.length > 0
            width: parent.width
            text: root.detail
            color: Ui.textSecondary
            font.family: monoFontFamily
            font.pixelSize: Math.max(Ui.textCaption, 6.5 * root.uiScale)
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }
    }
}

