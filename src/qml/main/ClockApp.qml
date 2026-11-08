import QtQuick
import "components/UiTokens.js" as Ui

Item {
    id: root
    property color accent: "#ff3852"
    property real uiScale: 1.0
    property bool wide: width > height * 1.22

    Rectangle { anchors.fill: parent; color: Ui.background }

    Canvas {
        id: face
        x: root.wide ? 8 * root.uiScale : (parent.width - width) / 2
        y: root.wide ? (parent.height - height) / 2 : 7 * root.uiScale
        width: root.wide ? Math.min(parent.height - 16 * root.uiScale, parent.width * 0.57)
                         : Math.min(parent.width - 16 * root.uiScale, parent.height * 0.70)
        height: width
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d"), size = width, c = size / 2, r = size * 0.43
            var now = new Date()
            ctx.reset(); ctx.clearRect(0, 0, size, size)
            ctx.strokeStyle = "#172a32"; ctx.lineWidth = 5 * root.uiScale
            ctx.beginPath(); ctx.arc(c, c, r + 8 * root.uiScale, 0, Math.PI * 2); ctx.stroke()
            ctx.strokeStyle = "#526873"; ctx.lineWidth = Math.max(1, 1.2 * root.uiScale)
            ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke()
            for (var i = 0; i < 60; i++) {
                var a = i * Math.PI / 30 - Math.PI / 2, major = i % 5 === 0
                var inner = r - (major ? 13 : 6) * root.uiScale
                ctx.strokeStyle = major ? root.accent : "#2a3d45"; ctx.lineWidth = major ? 2.2 * root.uiScale : 1
                ctx.beginPath(); ctx.moveTo(c + Math.cos(a) * inner, c + Math.sin(a) * inner); ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r); ctx.stroke()
            }
            ctx.fillStyle = "#8498a1"; ctx.textAlign = "center"; ctx.textBaseline = "middle"
            ctx.font = "bold " + Math.max(7, 8 * root.uiScale) + "px monospace"
            for (var n = 1; n <= 12; n++) {
                var na = n * Math.PI / 6 - Math.PI / 2
                ctx.fillText(String(n), c + Math.cos(na) * r * 0.72, c + Math.sin(na) * r * 0.72)
            }
            function hand(value, maximum, length, lineWidth, color, tail) {
                var angle = value / maximum * Math.PI * 2 - Math.PI / 2
                ctx.strokeStyle = color; ctx.lineWidth = lineWidth * root.uiScale; ctx.lineCap = "round"
                ctx.beginPath(); ctx.moveTo(c - Math.cos(angle) * r * tail, c - Math.sin(angle) * r * tail); ctx.lineTo(c + Math.cos(angle) * r * length, c + Math.sin(angle) * r * length); ctx.stroke()
            }
            var seconds = now.getSeconds() + now.getMilliseconds() / 1000
            var minutes = now.getMinutes() + seconds / 60, hours = (now.getHours() % 12) + minutes / 60
            hand(hours, 12, 0.49, 4.3, "#edf3f5", 0.04)
            hand(minutes, 60, 0.70, 3.0, "#a9bac2", 0.05)
            hand(seconds, 60, 0.82, 1.1, root.accent, 0.15)
            ctx.fillStyle = "#020709"; ctx.strokeStyle = root.accent; ctx.lineWidth = 2 * root.uiScale
            ctx.beginPath(); ctx.arc(c, c, 5 * root.uiScale, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
        }
        Timer { interval: 100; running: root.visible; repeat: true; onTriggered: face.requestPaint() }
    }

    Item {
        id: digital
        x: root.wide ? face.x + face.width + 8 * root.uiScale : 0
        y: root.wide ? 0 : face.y + face.height + 2 * root.uiScale
        width: root.wide ? parent.width - x : parent.width
        height: root.wide ? parent.height : parent.height - y

        Column {
            anchors.centerIn: parent
            spacing: 7 * root.uiScale
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: controller.currentTimeSeconds
            color: Ui.textPrimary
                font.family: displayFontFamily
                font.pixelSize: Math.min(root.wide ? digital.width * 0.15 : root.width * 0.075, 25 * root.uiScale)
                font.bold: true
                font.letterSpacing: 2 * root.uiScale
            }
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: Math.min(digital.width * 0.72, 190 * root.uiScale); height: 1; color: root.accent }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: controller.currentDate
                color: "#91a3ac"
                font.family: monoFontFamily
                font.pixelSize: Math.max(6, Math.min(9 * root.uiScale, digital.width * 0.045))
                font.letterSpacing: 1.2 * root.uiScale
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Qt.formatDateTime(new Date(), "dddd").toUpperCase() + "  ·  LOCAL TIME"
                color: "#586d76"
                font.family: monoFontFamily
                font.pixelSize: Math.max(5, 5.5 * root.uiScale)
                font.letterSpacing: 0.8 * root.uiScale
            }
        }
    }
}
