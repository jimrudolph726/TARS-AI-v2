import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property color accent: "#ff3852"
    property real uiScale: 1.0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8 * root.uiScale
        spacing: 5 * root.uiScale

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Canvas {
                id: face
                anchors.centerIn: parent
                width: Math.min(parent.width, parent.height) * 0.82
                height: width

                onPaint: {
                    var ctx = getContext("2d")
                    var w = width
                    var c = w / 2
                    var r = w * 0.44
                    var now = new Date()
                    ctx.reset()
                    ctx.strokeStyle = "#30444d"
                    ctx.lineWidth = Math.max(1, 1.2 * root.uiScale)
                    ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke()
                    for (var i = 0; i < 60; ++i) {
                        var a = i * Math.PI / 30 - Math.PI / 2
                        var major = i % 5 === 0
                        var inner = r - (major ? 13 : 7) * root.uiScale
                        ctx.strokeStyle = major ? root.accent : "#263840"
                        ctx.lineWidth = major ? 2 * root.uiScale : 1
                        ctx.beginPath()
                        ctx.moveTo(c + Math.cos(a) * inner, c + Math.sin(a) * inner)
                        ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r)
                        ctx.stroke()
                    }
                    function hand(value, maximum, length, width, color) {
                        var a = value / maximum * Math.PI * 2 - Math.PI / 2
                        ctx.strokeStyle = color
                        ctx.lineWidth = width * root.uiScale
                        ctx.lineCap = "round"
                        ctx.beginPath(); ctx.moveTo(c, c)
                        ctx.lineTo(c + Math.cos(a) * r * length, c + Math.sin(a) * r * length)
                        ctx.stroke()
                    }
                    var seconds = now.getSeconds() + now.getMilliseconds() / 1000
                    var minutes = now.getMinutes() + seconds / 60
                    var hours = (now.getHours() % 12) + minutes / 60
                    hand(hours, 12, 0.50, 4, "#edf3f5")
                    hand(minutes, 60, 0.72, 3, "#a9bac2")
                    hand(seconds, 60, 0.82, 1, root.accent)
                    ctx.fillStyle = root.accent
                    ctx.beginPath(); ctx.arc(c, c, 4 * root.uiScale, 0, Math.PI * 2); ctx.fill()
                }

                Timer { interval: 100; running: true; repeat: true; onTriggered: face.requestPaint() }
            }
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: controller.currentTimeSeconds
            color: "#edf3f5"
            font.family: displayFontFamily
            font.pixelSize: 23 * root.uiScale
            font.bold: true
            font.letterSpacing: 2 * root.uiScale
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: controller.currentDate
            color: "#91a3ac"
            font.family: monoFontFamily
            font.pixelSize: 8 * root.uiScale
            font.letterSpacing: 1.4 * root.uiScale
        }
    }
}
