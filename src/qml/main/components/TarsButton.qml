import QtQuick
import QtQuick.Controls
import "UiTokens.js" as Ui

Button {
    id: root

    property string iconText: ""
    property color accent: "#ff3852"
    property bool selected: false
    property bool danger: false
    property string badgeText: ""
    property color badgeColor: accent
    property real uiScale: 1.0
    property bool dense: false
    property real iconPixelSize: Math.max(Ui.textLabel * uiScale, root.height * (dense ? 0.25 : 0.28))
    property real labelPixelSize: Math.max(Ui.textCaption * uiScale, root.height * (dense ? 0.12 : 0.13))

    implicitWidth: 96 * uiScale
    implicitHeight: Math.max(Ui.touchMin, Ui.touchMin * uiScale)

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: buttonContent.implicitHeight

        Column {
            id: buttonContent
            anchors.centerIn: parent
            spacing: root.iconText.length ? Ui.spaceXs * root.uiScale : 0

            Text {
                visible: root.iconText.length > 0
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.iconText
                color: root.enabled ? (root.selected || root.down ? root.accent : "#dce6ea") : Ui.disabled
                font.family: displayFontFamily
                font.pixelSize: root.iconPixelSize
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.text
                color: root.enabled ? Ui.textPrimary : Ui.disabled
                font.family: displayFontFamily
                font.pixelSize: root.labelPixelSize
                font.bold: true
                font.letterSpacing: 1.1 * root.uiScale
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    background: Rectangle {
        radius: Ui.radiusMd * root.uiScale
        color: root.down ? Ui.surfacePressed
             : root.hovered ? Ui.surfaceHover
             : root.selected ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.10)
             : "#0a151b"
        border.width: root.selected || root.visualFocus ? 2 : 1
        border.color: root.enabled ? root.accent : "#37434a"

        Rectangle {
            anchors.fill: parent
            anchors.margins: Ui.spaceXs * root.uiScale
            radius: Ui.radiusSm * root.uiScale
            color: "transparent"
            border.width: 1
            border.color: root.hovered || root.visualFocus ? "#485961" : "#1a2b32"
        }
    }

    Rectangle {
        visible: root.badgeText.length > 0
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Ui.spaceXs * root.uiScale
        height: 14 * root.uiScale
        width: badgeLabel.implicitWidth + 9 * root.uiScale
        radius: height / 2
        color: Qt.rgba(root.badgeColor.r, root.badgeColor.g, root.badgeColor.b, 0.13)
        border.color: root.enabled ? root.badgeColor : "#465259"

        Text {
            id: badgeLabel
            anchors.centerIn: parent
            text: root.badgeText
            color: root.enabled ? root.badgeColor : Ui.disabled
            font.family: monoFontFamily
            font.pixelSize: Ui.textCaption * root.uiScale
            font.bold: true
        }
    }

    scale: down ? 0.975 : 1.0
    Behavior on scale { NumberAnimation { duration: 80 } }
}
