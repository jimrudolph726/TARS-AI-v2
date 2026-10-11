import QtQuick

Item {
    id: root
    property real uiScale: 1.0
    property var history: []
    property var states: []

    Timer {
        interval: 80
        running: true
        repeat: true
        onTriggered: {
            var next = root.history.slice(0)
            var stateNext = root.states.slice(0)
            next.push(controller.audioLevel)
            stateNext.push(controller.tarsState)
            var maximum = Math.max(80, Math.floor(chart.width / 3))
            if (next.length > maximum) next.splice(0, next.length - maximum)
            if (stateNext.length > maximum) stateNext.splice(0, stateNext.length - maximum)
            root.history = next
            root.states = stateNext
            chart.requestPaint()
        }
    }

    Canvas {
        id: chart
        anchors.fill: parent
        anchors.margins: 8 * root.uiScale

        onPaint: {
            var ctx = getContext("2d")
            var w = width
            var h = height
            var labelW = 55 * root.uiScale
            var graphW = w - labelW - 5 * root.uiScale
            var laneH = h / 4
            ctx.reset()
            ctx.fillStyle = "#050d11"; ctx.fillRect(0, 0, w, h)
            var labels = ["INPUT", "SPEECH", "TTS", "STATE"]
            for (var lane = 0; lane < 4; ++lane) {
                var top = lane * laneH
                ctx.strokeStyle = "#263840"; ctx.lineWidth = 1
                ctx.strokeRect(labelW, top + 1, graphW, laneH - 2)
                ctx.fillStyle = "#8799a2"
                ctx.font = Math.max(7, 7 * root.uiScale) + "px monospace"
                ctx.fillText(labels[lane], 4 * root.uiScale, top + laneH / 2 + 3 * root.uiScale)
            }
            if (!root.history.length) return
            var dx = graphW / Math.max(1, root.history.length - 1)
            function lineForLane(lane, color, valueFn) {
                var cy = lane * laneH + laneH / 2
                ctx.strokeStyle = color; ctx.lineWidth = Math.max(1, 1.4 * root.uiScale)
                ctx.beginPath()
                for (var i = 0; i < root.history.length; ++i) {
                    var value = valueFn(i)
                    var x = labelW + i * dx
                    var y = cy - value * laneH * 0.38
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                }
                ctx.stroke()
            }
            lineForLane(0, "#dfe8ec", function(i) { return Math.min(1, root.history[i]) })
            lineForLane(1, "#2aff8a", function(i) { return root.history[i] > 0.22 ? 0.9 : 0.05 })
            lineForLane(2, "#b782ff", function(i) { return root.states[i] === "SPEAKING" ? 0.9 : 0.05 })
            var stateColors = {"STANDBY":"#50616a", "LISTENING":"#2aff8a", "THINKING":"#ffc857", "SPEAKING":"#ff3852"}
            var stateTop = 3 * laneH + laneH * 0.25
            for (var s = 0; s < root.states.length; ++s) {
                ctx.fillStyle = stateColors[root.states[s]] || "#50616a"
                ctx.fillRect(labelW + s * dx, stateTop, Math.max(2, dx + 1), laneH * 0.5)
            }
        }
    }

    Text {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12 * root.uiScale
        text: "LEVEL " + Math.round(controller.audioLevel * 100) + "%  ·  " + controller.tarsState
        color: "#b9c7cd"
        font.family: monoFontFamily
        font.pixelSize: 6.5 * root.uiScale
    }
}
