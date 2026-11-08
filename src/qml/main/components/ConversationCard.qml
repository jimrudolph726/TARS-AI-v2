import QtQuick
import "UiTokens.js" as Ui

Rectangle {
    id: root

    property string speaker: "TARS"
    property string message: "All systems nominal."
    property string messageTime: "03:20 PM"
    property bool isTars: true
    property color accent: "#ff3852"
    property real uiScale: 1.0

    radius: Ui.radiusMd * uiScale
    color: Ui.surfaceRaised
    border.width: isTars ? 1.4 : 1
    border.color: isTars ? accent : "#31505e"

    Rectangle {
        id: avatar
        width: Math.min(52 * root.uiScale, root.height - 16 * root.uiScale)
        height: width
        radius: Ui.radiusMd * root.uiScale
        anchors.left: parent.left
        anchors.leftMargin: 10 * root.uiScale
        anchors.verticalCenter: parent.verticalCenter
        color: "#0c1820"
        border.width: 1
        border.color: root.accent

        Text {
            anchors.centerIn: parent
            text: root.isTars ? "T" : "U"
            color: root.isTars ? root.accent : "#c8d7df"
            font.family: displayFontFamily
            font.pixelSize: 22 * root.uiScale
            font.bold: true
        }
    }

    Text {
        id: speakerLabel
        anchors.left: avatar.right
        anchors.leftMargin: 11 * root.uiScale
        anchors.top: parent.top
        anchors.topMargin: 10 * root.uiScale
        text: root.speaker
        color: root.accent
        font.family: displayFontFamily
        font.pixelSize: Ui.textHeading * root.uiScale
        font.bold: true
        font.letterSpacing: 1.8 * root.uiScale
    }

    Text {
        anchors.right: parent.right
        anchors.rightMargin: 11 * root.uiScale
        anchors.verticalCenter: speakerLabel.verticalCenter
        text: root.messageTime
        color: "#92a3ac"
        font.family: monoFontFamily
        font.pixelSize: Ui.textBody * root.uiScale
        font.letterSpacing: 1.0 * root.uiScale
    }

    Text {
        anchors.left: speakerLabel.left
        anchors.right: parent.right
        anchors.rightMargin: 12 * root.uiScale
        anchors.top: speakerLabel.bottom
        anchors.topMargin: 7 * root.uiScale
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8 * root.uiScale
        text: root.message
        color: Ui.textPrimary
        font.family: monoFontFamily
        font.pixelSize: Math.max(10, 13 * root.uiScale)
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
        elide: Text.ElideRight
        maximumLineCount: root.width < 360 * root.uiScale ? 4 : 3
    }
}
