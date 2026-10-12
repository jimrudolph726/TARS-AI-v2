import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    default property alias controlData: controlHost.data
    property string label: "SETTING"
    property string description: ""
    property string statusText: ""
    property color accent: "#ff3852"
    property real uiScale: 1.0

    implicitWidth: 320 * uiScale
    implicitHeight: 50 * uiScale
    radius: 5 * uiScale
    color: enabled ? "#071116" : "#050b0e"
    border.color: enabled ? "#2d424b" : "#202d33"
    opacity: enabled ? 1.0 : 0.66

    RowLayout {
        anchors.fill: parent
        anchors.margins: 8 * root.uiScale
        spacing: 9 * root.uiScale

        Column {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2 * root.uiScale

            Row {
                spacing: 6 * root.uiScale
                Text {
                    text: root.label
                    color: root.enabled ? "#edf3f5" : "#68777e"
                    font.family: displayFontFamily
                    font.pixelSize: 8 * root.uiScale
                    font.bold: true
                    font.letterSpacing: 0.8 * root.uiScale
                }
                Text {
                    visible: root.statusText.length > 0
                    text: root.statusText
                    color: root.enabled ? root.accent : "#58656b"
                    font.family: monoFontFamily
                    font.pixelSize: 6 * root.uiScale
                    font.bold: true
                }
            }
            Text {
                width: parent.width
                visible: root.description.length > 0
                text: root.description
                color: root.enabled ? "#7f929b" : "#536168"
                font.family: monoFontFamily
                font.pixelSize: 6 * root.uiScale
                elide: Text.ElideRight
            }
        }

        Item {
            id: controlHost
            Layout.preferredWidth: Math.max(82 * root.uiScale, childrenRect.width)
            Layout.fillHeight: true
            enabled: root.enabled
        }
    }
}

