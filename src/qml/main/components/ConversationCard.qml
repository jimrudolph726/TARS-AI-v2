import QtQuick

Rectangle {
    id: root

    property string speaker: "TARS"
    property string message: "All systems nominal."
    property string messageTime: "03:20 PM"
    property bool isTars: true
    property color accent: "#ff3852"
    property real uiScale: 1.0

    radius: 7 * uiScale
    color: "#09151b"
    border.width: isTars ? 1.4 : 1
    border.color: isTars ? accent : "#31505e"

    Rectangle {
        id: avatar
        width: 48 * root.uiScale
        height: width
        radius: 6 * root.uiScale
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
        font.pixelSize: 11 * root.uiScale
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
        font.pixelSize: 8 * root.uiScale
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
        color: "#edf3f5"
        font.family: monoFontFamily
        font.pixelSize: 13 * root.uiScale
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
        elide: Text.ElideRight
        maximumLineCount: 2
    }
}
