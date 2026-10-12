import QtQuick
import QtQuick.Controls

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
        width: parent.width - 30 * root.uiScale
        spacing: 8 * root.uiScale

        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.state === "loading"
            running: visible
            width: 30 * root.uiScale
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
            font.pixelSize: 11 * root.uiScale
            font.bold: true
            font.letterSpacing: 1.1 * root.uiScale
        }
        Text {
            visible: root.detail.length > 0
            width: parent.width
            text: root.detail
            color: "#82949c"
            font.family: monoFontFamily
            font.pixelSize: 6.5 * root.uiScale
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }
    }
}

