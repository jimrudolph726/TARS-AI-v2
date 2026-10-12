import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: root

    property color accent: "#ff3852"
    property real uiScale: 1.0
    property string activeFeed: "feed"
    readonly property bool hasWeather: controller.dashboardWeather.temperature !== undefined
    readonly property var selectedFeed: activeFeed === "news" ? controller.dashboardNews
        : activeFeed === "calendar" ? controller.dashboardCalendar
        : controller.dashboardFeed

    function weatherGlyph(code) {
        if (code === 0 || code === 1) return "SUN"
        if (code === 2 || code === 3 || code === 45 || code === 48) return "CLD"
        if (code >= 71 && code <= 86) return "SNW"
        if (code >= 95) return "STM"
        return "RAIN"
    }

    Component.onCompleted: controller.refreshDashboard()

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: controller.nextDashboardQuote()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5 * root.uiScale
        spacing: 5 * root.uiScale

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 76 * root.uiScale
            Layout.maximumHeight: 76 * root.uiScale
            spacing: 5 * root.uiScale

            StatusCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                Layout.preferredWidth: 1.25
                label: root.hasWeather ? controller.dashboardWeather.location.toUpperCase() : "WEATHER"
                value: root.hasWeather
                    ? controller.dashboardWeather.temperature + controller.dashboardWeather.unit
                    : "--"
                detail: root.hasWeather
                    ? controller.dashboardWeather.condition.toUpperCase()
                        + "  ·  FEELS " + controller.dashboardWeather.feelsLike + controller.dashboardWeather.unit
                    : controller.dashboardLoading ? "FETCHING FORECAST" : "WEATHER UNAVAILABLE"
                iconText: root.hasWeather ? root.weatherGlyph(controller.dashboardWeather.code) : "WX"
                badgeText: root.hasWeather ? controller.dashboardWeather.humidity + "% HUM" : ""
                accent: root.hasWeather ? "#64b5f6" : "#66757c"
                valuePixelSize: 18 * root.uiScale
                uiScale: root.uiScale
            }

            StatusCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                Layout.preferredWidth: 1
                label: "NEXT EVENT"
                value: controller.dashboardCalendar.length
                    ? controller.dashboardCalendar[0].title
                    : controller.dashboardCalendarConfigured ? "NO EVENTS" : "NOT CONFIGURED"
                detail: controller.dashboardCalendar.length
                    ? controller.dashboardCalendar[0].meta
                    : controller.dashboardCalendarConfigured
                        ? "NEXT " + controller.dashboardConfigFile.toUpperCase()
                        : "ADD ICS URL TO DASHBOARD.INI"
                iconText: "CAL"
                accent: controller.dashboardCalendar.length ? "#ffc857" : "#66757c"
                valuePixelSize: 10 * root.uiScale
                uiScale: root.uiScale
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 43 * root.uiScale
            Layout.maximumHeight: 43 * root.uiScale
            spacing: 4 * root.uiScale

            Repeater {
                model: controller.dashboardForecast
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 4 * root.uiScale
                    color: "#071116"
                    border.color: "#2b414a"

                    Column {
                        anchors.centerIn: parent
                        spacing: 1 * root.uiScale
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.day
                            color: "#8fa1aa"
                            font.family: monoFontFamily
                            font.pixelSize: 5.5 * root.uiScale
                            font.bold: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.high + "° / " + modelData.low + "°"
                            color: "#edf3f5"
                            font.family: displayFontFamily
                            font.pixelSize: 7 * root.uiScale
                            font.bold: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.rain + "% RAIN"
                            color: "#64b5f6"
                            font.family: monoFontFamily
                            font.pixelSize: 5 * root.uiScale
                        }
                    }
                }
            }

            AppStateView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: controller.dashboardForecast.length === 0
                state: controller.dashboardLoading ? "loading" : "empty"
                title: controller.dashboardLoading ? "LOADING FORECAST" : "NO FORECAST"
                uiScale: root.uiScale * 0.72
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 48 * root.uiScale
            Layout.maximumHeight: 48 * root.uiScale
            radius: 4 * root.uiScale
            color: "#071116"
            border.color: "#30434b"

            Column {
                anchors.centerIn: parent
                width: parent.width - 18 * root.uiScale
                spacing: 3 * root.uiScale
                Text {
                    width: parent.width
                    text: "“" + controller.dashboardQuote.text + "”"
                    color: "#dce6ea"
                    font.family: displayFontFamily
                    font.pixelSize: 7.5 * root.uiScale
                    font.bold: true
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    width: parent.width
                    text: "— " + controller.dashboardQuote.author
                    color: root.accent
                    font.family: monoFontFamily
                    font.pixelSize: 5.5 * root.uiScale
                    horizontalAlignment: Text.AlignHCenter
                }
            }
            MouseArea {
                anchors.fill: parent
                onClicked: controller.nextDashboardQuote()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 27 * root.uiScale
            Layout.maximumHeight: 27 * root.uiScale
            spacing: 4 * root.uiScale

            Repeater {
                model: [
                    { id: "feed", label: "ALL FEED" },
                    { id: "news", label: "NEWS" },
                    { id: "calendar", label: "CALENDAR" }
                ]
                delegate: TarsButton {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: modelData.label
                    iconText: ""
                    labelPixelSize: 5.5 * root.uiScale
                    selected: root.activeFeed === modelData.id
                    accent: root.accent
                    onClicked: root.activeFeed = modelData.id
                }
            }
            TarsButton {
                Layout.preferredWidth: 72 * root.uiScale
                Layout.fillHeight: true
                text: "REFRESH"
                iconText: "R"
                iconPixelSize: 7 * root.uiScale
                labelPixelSize: 5 * root.uiScale
                enabled: !controller.dashboardLoading
                onClicked: controller.refreshDashboard()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                anchors.fill: parent
                visible: root.selectedFeed.length > 0
                clip: true
                spacing: 3 * root.uiScale
                model: root.selectedFeed

                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 38 * root.uiScale
                    radius: 4 * root.uiScale
                    color: "#071116"
                    border.color: modelData.kind === "CALENDAR" ? "#5e5329" : "#263c45"

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 6 * root.uiScale
                        spacing: 7 * root.uiScale

                        Text {
                            text: modelData.kind === "CALENDAR" ? "CAL" : "RSS"
                            color: modelData.kind === "CALENDAR" ? "#ffc857" : "#64b5f6"
                            font.family: displayFontFamily
                            font.pixelSize: 7 * root.uiScale
                            font.bold: true
                        }
                        Column {
                            Layout.fillWidth: true
                            spacing: 2 * root.uiScale
                            Text {
                                width: parent.width
                                text: modelData.title
                                color: "#edf3f5"
                                font.family: displayFontFamily
                                font.pixelSize: 7 * root.uiScale
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                text: modelData.meta + (modelData.detail.length ? "  ·  " + modelData.detail : "")
                                color: "#778a93"
                                font.family: monoFontFamily
                                font.pixelSize: 5.5 * root.uiScale
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            AppStateView {
                anchors.fill: parent
                visible: root.selectedFeed.length === 0
                state: controller.dashboardLoading ? "loading"
                    : controller.dashboardError.length ? "error"
                    : root.activeFeed === "calendar" && !controller.dashboardCalendarConfigured
                        ? "disabled"
                    : "empty"
                title: controller.dashboardLoading ? "UPDATING DASHBOARD"
                    : controller.dashboardError.length ? "FEED UNAVAILABLE"
                    : root.activeFeed === "calendar" && !controller.dashboardCalendarConfigured
                        ? "CALENDAR NOT CONFIGURED"
                    : "NO ITEMS AVAILABLE"
                detail: controller.dashboardError.length ? controller.dashboardError
                    : root.activeFeed === "calendar" && !controller.dashboardCalendarConfigured
                        ? "Add an ICS URL to " + controller.dashboardConfigFile + "."
                    : "Pull to refresh or check the network connection."
                uiScale: root.uiScale
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: 8 * root.uiScale
            text: "SOURCE " + controller.dashboardConfigFile.toUpperCase()
                + (controller.dashboardLastUpdated.length ? "  ·  UPDATED " + controller.dashboardLastUpdated : "")
            color: "#51646d"
            font.family: monoFontFamily
            font.pixelSize: 5 * root.uiScale
            horizontalAlignment: Text.AlignRight
        }
    }
}

