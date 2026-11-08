import QtQuick
import "UiTokens.js" as Ui

Rectangle {
    id: root

    property string label: "STATUS"
    property string value: "--"
    property string detail: ""
    property string iconText: ""
    property string badgeText: ""
    property color accent: "#ff3852"
    property real uiScale: 1.0
    property real labelPixelSize: 7 * uiScale
    property real valuePixelSize: 20 * uiScale
    property real detailPixelSize: 6 * uiScale
    readonly property bool compact: height < 58 * uiScale

    implicitWidth: 150 * uiScale
    implicitHeight: 90 * uiScale
    radius: Ui.radiusSm * uiScale
    color: enabled ? "#071116" : "#050b0e"
    border.color: enabled ? "#31444d" : "#202d33"
    opacity: enabled ? 1.0 : 0.64

    Text {
        visible: root.iconText.length > 0
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: Ui.spaceMd * root.uiScale
        text: root.iconText
        color: root.accent
        font.family: displayFontFamily
        font.pixelSize: 10 * root.uiScale
        font.bold: true
    }

    Rectangle {
        visible: root.badgeText.length > 0
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Ui.spaceSm * root.uiScale
        width: badgeLabel.implicitWidth + 10 * root.uiScale
        height: 15 * root.uiScale
        radius: height / 2
        color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.12)
        border.color: root.accent

        Text {
            id: badgeLabel
            anchors.centerIn: parent
            text: root.badgeText
            color: root.accent
            font.family: monoFontFamily
            font.pixelSize: 5.5 * root.uiScale
            font.bold: true
        }
    }

    Column {
        anchors.centerIn: parent
        width: parent.width - 16 * root.uiScale
        spacing: root.compact ? Ui.space2xs * root.uiScale : Ui.spaceXs * root.uiScale

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.label
            color: root.enabled ? "#8fa1aa" : Ui.disabled
            font.family: monoFontFamily
            font.pixelSize: root.labelPixelSize
            font.letterSpacing: 1.1 * root.uiScale
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.value
            color: root.enabled ? root.accent : "#617078"
            font.family: displayFontFamily
            font.pixelSize: root.compact ? Math.min(root.valuePixelSize, 12 * root.uiScale) : root.valuePixelSize
            font.bold: true
        }
        Text {
            width: parent.width
            visible: root.detail.length > 0 && !root.compact
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            text: root.detail
            color: root.enabled ? "#667b84" : "#4f5d63"
            font.family: monoFontFamily
            font.pixelSize: root.detailPixelSize
        }
    }
}

