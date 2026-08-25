import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "cassian.vct-scoreline"

  readonly property string fetchScriptPath: {
    const url = String(Qt.resolvedUrl("./vlr.py"))
    return url.indexOf("file://") === 0 ? decodeURIComponent(url.substring(7)) : url
  }

  property bool opened: false
  property bool loading: false
  property var liveMatches: []
  property var upcomingMatches: []
  property string errorText: ""
  property string lastUpdated: ""

  readonly property color fg: Color.popups.text
  readonly property color dimText: Qt.darker(fg, 1.4)
  readonly property color dimmerText: Qt.darker(fg, 1.75)
  readonly property color liveColor: Color.urgent
  readonly property color cardFill: Qt.rgba(fg.r, fg.g, fg.b, 0.045)
  readonly property color cardBorder: Qt.rgba(fg.r, fg.g, fg.b, 0.13)
  readonly property color barFg: bar ? bar.barForeground : Color.foreground
  readonly property color barStatusColor: liveMatches.length > 0 || errorText !== "" ? liveColor : barFg

  readonly property int liveRefreshSeconds: boundedSetting("liveRefreshSeconds", 30, 15, 300)
  readonly property int idleRefreshSeconds: boundedSetting("idleRefreshSeconds", 120, 30, 900)
  readonly property int refreshInterval: (liveMatches.length > 0 ? liveRefreshSeconds : idleRefreshSeconds) * 1000

  // Hard ceilings for data received from the helper process and rendered remotely.
  readonly property int maxSnapshotChars: 256 * 1024
  readonly property int maxErrorChars: 8 * 1024
  readonly property int maxListItems: 12
  readonly property int maxFieldChars: 300

  readonly property string barTooltip: {
    if (loading && lastUpdated === "") return "VCT - loading VLR.gg"
    if (liveMatches.length > 0) {
      const match = liveMatches[0]
      const suffix = liveMatches.length > 1 ? " (" + liveMatches.length + " live)" : ""
      return "LIVE VCT - " + teamName(match, 0) + " " + seriesScore(match, 0)
        + " : " + seriesScore(match, 1) + " " + teamName(match, 1) + suffix
    }
    if (errorText !== "") return "VCT - " + firstLine(errorText)
    if (upcomingMatches.length > 0) {
      return "VCT - next: " + teamName(upcomingMatches[0], 0) + " vs " + teamName(upcomingMatches[0], 1)
    }
    return "VCT - no live match"
  }

  function boundedSetting(key, fallback, minimum, maximum) {
    let value = parseInt(String(setting(key, fallback)), 10)
    if (!isFinite(value)) value = fallback
    return Math.max(minimum, Math.min(maximum, value))
  }

  function firstLine(value) {
    return String(value || "").split("\n")[0]
  }

  function teamAt(match, index) {
    if (!match || !match.teams) return null
    let team = match.teams[index]
    if (!team && typeof match.teams.at === "function") team = match.teams.at(index)
    return team || null
  }

  function teamName(match, index) {
    const team = teamAt(match, index)
    return team && team.name ? String(team.name) : "TBD"
  }

  function teamAbbreviation(match, index) {
    const name = teamName(match, index)
    const known = {
      "Evil Geniuses": "EG",
      "Gen.G": "GEN",
      "Global Esports": "GE",
      "KIWOOM DRX": "DRX",
      "LEVIATÁN": "LEV",
      "Nongshim RedForce": "NS",
      "Paper Rex": "PRX"
    }
    if (known[name]) return known[name]

    const words = name.split(/\s+/).filter(function(word) { return word !== "" })
    if (words.length === 1) {
      return name.length <= 6 ? name.toUpperCase() : name.substring(0, 3).toUpperCase()
    }

    const last = words[words.length - 1]
    if (/^[A-Z0-9]{2,5}$/.test(last)) return last
    if (words.length === 2 && /^.{1,3}$/.test(words[0]) && /^esports$/i.test(words[1])) {
      return words[0].toUpperCase()
    }
    return words.map(function(word) { return word.charAt(0) }).join("").substring(0, 5).toUpperCase()
  }

  function score(team, key) {
    if (!team || team[key] === undefined || team[key] === null || team[key] === "") return "-"
    return String(team[key])
  }

  function mapScore(match, index) {
    return score(teamAt(match, index), "mapScore")
  }

  function seriesScore(match, index) {
    return score(teamAt(match, index), "seriesScore")
  }

  function scoreColor(match, index) {
    return match && Number(match.attackingTeam) === index ? liveColor : fg
  }

  function attackText(match) {
    if (!match || match.attackingTeam === undefined || match.attackingTeam === null) return "ATTACKING SIDE UNKNOWN"
    return "ATTACKING: " + teamName(match, Number(match.attackingTeam)).toUpperCase()
  }

  function matchDayPrefix(match) {
    const label = String(match && match.date ? match.date : "")
    const months = {
      january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
      july: 7, august: 8, september: 9, october: 10, november: 11, december: 12
    }
    const lower = label.toLowerCase()
    if (/\btomorrow\b/.test(lower) || /\btoday\b/.test(lower)) {
      const day = new Date()
      if (/\btomorrow\b/.test(lower)) day.setDate(day.getDate() + 1)
      return (day.getMonth() + 1) + "/" + day.getDate()
    }
    const found = label.match(/([A-Za-z]+)\.?\s+(\d{1,2})/)
    if (!found) return ""
    const month = months[found[1].toLowerCase()]
    return month ? month + "/" + parseInt(found[2], 10) : ""
  }

  function matchTimeLabel(match) {
    const time = String(match && match.time ? match.time : "TBD")
    const eta = String(match && match.eta ? match.eta : "")
    if (!/\b\d+\s*d\b/.test(eta)) return time
    const prefix = matchDayPrefix(match)
    return prefix === "" ? time : prefix + "  " + time
  }

  function openMatch(match) {
    const url = String(match && match.url ? match.url : "")
    if (!/^https:\/\/(?:www\.)?vlr\.gg\/\d+(?:\/|$)/.test(url)) return
    Qt.openUrlExternally(url)
    close()
  }

  function refresh() {
    if (fetchProcess.running) return
    loading = true
    fetchProcess.command = ["python3", fetchScriptPath]
    fetchProcess.running = true
  }

  function applySnapshot(snapshot) {
    if (!snapshot || snapshot.ok !== true) {
      errorText = clampRemoteText(snapshot && snapshot.error ? snapshot.error : "Could not read VLR.gg data")
      return
    }
    liveMatches = Array.isArray(snapshot.live) ? snapshot.live.slice(0, maxListItems) : []
    upcomingMatches = Array.isArray(snapshot.upcoming) ? snapshot.upcoming.slice(0, maxListItems) : []
    errorText = clampRemoteText(snapshot.warning)
    lastUpdated = new Date().toLocaleTimeString(Qt.locale(), "HH:mm:ss")
  }

  function clampRemoteText(value) {
    return String(value || "").substring(0, maxFieldChars)
  }

  function open() {
    opened = true
    refresh()
  }

  function close() { opened = false }
  function toggle() { opened ? close() : open() }
  function closeForPopoutSwitch() { close() }

  readonly property bool popoutSwitchClosing: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Valorant-style crosshairs glyph (Nerd Font)
    text: "󰆣"
    foreground: root.barStatusColor
    slotSize: Style.bar.statusSlot
    tooltipText: root.barTooltip
    onPressed: function(btn) { root.toggle() }
  }

  Timer {
    id: refreshTimer
    interval: root.refreshInterval
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Process {
    id: fetchProcess
    property string snapshotData: ""
    property string errorData: ""
    property bool snapshotOverflowed: false
    property bool errorOverflowed: false

    function resetBuffers() {
      snapshotData = ""
      errorData = ""
      snapshotOverflowed = false
      errorOverflowed = false
    }

    stdout: SplitParser {
      id: fetchStdout
      splitMarker: "\n"

      onRead: function(data) {
        const chunk = String(data)
        if (chunk === "" || fetchProcess.snapshotOverflowed) return
        if (fetchProcess.snapshotData.length + chunk.length > root.maxSnapshotChars) {
          fetchProcess.snapshotOverflowed = true
          fetchProcess.snapshotData = ""
          return
        }
        fetchProcess.snapshotData += chunk
      }
    }

    stderr: SplitParser {
      id: fetchStderr
      splitMarker: "\n"

      onRead: function(data) {
        const chunk = String(data)
        if (chunk === "" || fetchProcess.errorOverflowed) return
        const merged = fetchProcess.errorData === ""
          ? chunk : fetchProcess.errorData + "\n" + chunk
        if (merged.length > root.maxErrorChars) {
          fetchProcess.errorOverflowed = true
          fetchProcess.errorData = ""
          return
        }
        fetchProcess.errorData = merged
      }
    }

    onStarted: fetchProcess.resetBuffers()

    onExited: function(exitCode) {
      root.loading = false
      if (fetchProcess.snapshotOverflowed) {
        root.errorText = "VLR.gg sent more data than expected"
        fetchProcess.resetBuffers()
        return
      }
      const output = fetchProcess.snapshotData.trim()
      if (output === "") {
        const stderr = fetchProcess.errorData.trim()
        root.errorText = fetchProcess.errorOverflowed
          ? "VLR.gg reported an error"
          : (stderr !== "" ? root.firstLine(stderr) : "VLR.gg returned no data")
        fetchProcess.resetBuffers()
        return
      }
      try {
        root.applySnapshot(JSON.parse(output))
      } catch (error) {
        root.errorText = "Could not parse VLR.gg response"
      }
      fetchProcess.resetBuffers()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: fittedContentWidth(Style.space(380))
    contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(680))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTextKey: function(text) {
        if (text === "r" || text === "R") root.refresh()
      }

      Flickable {
        id: contentScroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
          id: contentColumn
          width: contentScroll.width
          spacing: Style.space(10)

          RowLayout {
            Layout.fillWidth: true
            spacing: Style.space(7)

            Text {
              text: "VCT SCORELINE"
              color: root.fg
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }

            Text {
              text: "VLR.GG"
              color: root.dimmerText
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
            }

            Item { Layout.fillWidth: true }

            Text {
              visible: root.lastUpdated !== ""
              text: root.lastUpdated
              color: root.dimmerText
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
            }

            PanelActionButton {
              iconText: "󰑐"
              tooltipText: "Refresh VLR.gg"
              enabled: !root.loading
              onClicked: root.refresh()
            }

            PanelActionButton {
              iconText: "󰅙"
              tooltipText: "Close"
              onClicked: root.close()
            }
          }

          PanelSeparator { Layout.fillWidth: true }

          Rectangle {
            visible: root.errorText !== ""
            Layout.fillWidth: true
            implicitHeight: warningText.implicitHeight + Style.space(16)
            radius: Style.cornerRadius
            color: Qt.rgba(root.liveColor.r, root.liveColor.g, root.liveColor.b, 0.08)
            border.width: 1
            border.color: Qt.rgba(root.liveColor.r, root.liveColor.g, root.liveColor.b, 0.3)

            Text {
              id: warningText
              anchors.fill: parent
              anchors.margins: Style.space(8)
              text: root.errorText
              textFormat: Text.PlainText
              color: root.liveColor
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              wrapMode: Text.Wrap
            }
          }

          RowLayout {
            visible: root.liveMatches.length > 0
            Layout.fillWidth: true

            Text {
              text: "LIVE VCT"
              color: root.liveColor
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
            }

            Item { Layout.fillWidth: true }

            Text {
              visible: root.liveMatches.length > 1
              text: root.liveMatches.length + " MATCHES"
              color: root.dimmerText
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          Repeater {
            model: root.liveMatches

            Rectangle {
              id: liveCard
              required property var modelData
              Layout.fillWidth: true
              implicitHeight: liveColumn.implicitHeight + Style.space(20)
              radius: Style.cornerRadius
              color: liveMouse.containsMouse
                ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.085) : root.cardFill
              border.width: 1
              border.color: liveMouse.containsMouse
                ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.24) : root.cardBorder

              ColumnLayout {
                id: liveColumn
                anchors.fill: parent
                anchors.margins: Style.space(10)
                spacing: Style.space(7)

                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Style.space(1)

                    Text {
                      Layout.fillWidth: true
                      text: liveCard.modelData.event || "VCT"
                      textFormat: Text.PlainText
                      color: root.fg
                      font.family: Style.font.family
                      font.pixelSize: Style.font.body
                      font.bold: true
                      elide: Text.ElideRight
                    }

                    Text {
                      Layout.fillWidth: true
                      text: liveCard.modelData.series || "Live match"
                      textFormat: Text.PlainText
                      color: root.dimText
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      elide: Text.ElideRight
                    }
                  }

                  Rectangle {
                    implicitWidth: liveBadge.implicitWidth + Style.space(14)
                    implicitHeight: liveBadge.implicitHeight + Style.space(6)
                    radius: height / 2
                    color: Qt.rgba(root.liveColor.r, root.liveColor.g, root.liveColor.b, 0.14)

                    Text {
                      id: liveBadge
                      anchors.centerIn: parent
                      text: "LIVE"
                      color: root.liveColor
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.bold: true
                      font.letterSpacing: 1
                    }
                  }
                }

                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.fillWidth: true
                    text: root.teamName(liveCard.modelData, 0)
                    textFormat: Text.PlainText
                    color: root.fg
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                    elide: Text.ElideRight
                  }

                  Text {
                    text: root.mapScore(liveCard.modelData, 0)
                    textFormat: Text.PlainText
                    color: root.scoreColor(liveCard.modelData, 0)
                    font.family: Style.font.family
                    font.pixelSize: Style.font.display
                    font.bold: true
                    Layout.minimumWidth: Style.space(32)
                    horizontalAlignment: Text.AlignHCenter
                  }

                  ColumnLayout {
                    Layout.minimumWidth: Style.space(84)
                    spacing: Style.space(1)

                    Text {
                      Layout.fillWidth: true
                      text: root.seriesScore(liveCard.modelData, 0) + " : " + root.seriesScore(liveCard.modelData, 1)
                      textFormat: Text.PlainText
                      color: root.fg
                      font.family: Style.font.family
                      font.pixelSize: Style.font.subtitle
                      font.bold: true
                      horizontalAlignment: Text.AlignHCenter
                    }

                    Text {
                      Layout.fillWidth: true
                      text: "SERIES"
                      color: root.dimText
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.letterSpacing: 1
                      horizontalAlignment: Text.AlignHCenter
                    }

                    Text {
                      Layout.fillWidth: true
                      text: liveCard.modelData.map || "CURRENT MAP"
                      textFormat: Text.PlainText
                      color: root.dimText
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      horizontalAlignment: Text.AlignHCenter
                      elide: Text.ElideRight
                    }
                  }

                  Text {
                    text: root.mapScore(liveCard.modelData, 1)
                    textFormat: Text.PlainText
                    color: root.scoreColor(liveCard.modelData, 1)
                    font.family: Style.font.family
                    font.pixelSize: Style.font.display
                    font.bold: true
                    Layout.minimumWidth: Style.space(32)
                    horizontalAlignment: Text.AlignHCenter
                  }

                  Text {
                    Layout.fillWidth: true
                    text: root.teamName(liveCard.modelData, 1)
                    textFormat: Text.PlainText
                    color: root.fg
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideLeft
                  }
                }

                RowLayout {
                  Layout.fillWidth: true

                  Text {
                    text: liveCard.modelData.round ? "ROUND " + liveCard.modelData.round : "LIVE MAP"
                    textFormat: Text.PlainText
                    color: root.dimmerText
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                  }

                  Text {
                    Layout.fillWidth: true
                    text: root.attackText(liveCard.modelData)
                    textFormat: Text.PlainText
                    color: liveCard.modelData.attackingTeam === undefined || liveCard.modelData.attackingTeam === null
                      ? root.dimmerText : root.liveColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.bold: true
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideLeft
                  }
                }
              }

              MouseArea {
                id: liveMouse
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openMatch(liveCard.modelData)
              }
            }
          }

          ColumnLayout {
            visible: !root.loading && root.liveMatches.length === 0
            Layout.fillWidth: true
            spacing: 0

            Text {
              Layout.fillWidth: true
              text: "NO LIVE MATCH"
              color: root.dimText
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1
              horizontalAlignment: Text.AlignHCenter
            }
          }

          Text {
            visible: root.upcomingMatches.length > 0
            text: "UPCOMING VCT"
            color: root.dimText
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
          }

          Repeater {
            model: root.upcomingMatches

            Rectangle {
              id: upcomingCard
              required property var modelData
              Layout.fillWidth: true
              implicitHeight: upcomingRow.implicitHeight + Style.space(12)
              radius: Style.cornerRadius
              color: upcomingMouse.containsMouse
                ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.085) : root.cardFill
              border.width: 1
              border.color: upcomingMouse.containsMouse
                ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.24) : root.cardBorder

              RowLayout {
                id: upcomingRow
                anchors.fill: parent
                anchors.margins: Style.space(6)
                spacing: Style.space(7)

                Text {
                  Layout.fillWidth: true
                  text: root.teamAbbreviation(upcomingCard.modelData, 0)
                    + "  vs  " + root.teamAbbreviation(upcomingCard.modelData, 1)
                  textFormat: Text.PlainText
                  color: root.fg
                  font.family: Style.font.family
                  font.pixelSize: Style.font.body
                  font.bold: true
                  elide: Text.ElideRight
                }

                Text {
                  text: root.matchTimeLabel(upcomingCard.modelData)
                  textFormat: Text.PlainText
                  color: root.dimText
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }

                Rectangle {
                  implicitWidth: etaText.implicitWidth + Style.space(12)
                  implicitHeight: etaText.implicitHeight + Style.space(6)
                  radius: height / 2
                  color: Qt.rgba(root.liveColor.r, root.liveColor.g, root.liveColor.b, 0.12)

                  Text {
                    id: etaText
                    anchors.centerIn: parent
                    text: upcomingCard.modelData.eta || "TBD"
                    textFormat: Text.PlainText
                    color: root.liveColor
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    font.bold: true
                  }
                }

                Text {
                  text: "󰏌"
                  color: upcomingMouse.containsMouse ? root.fg : root.dimText
                  font.family: Style.font.family
                  font.pixelSize: Style.font.icon
                }
              }

              MouseArea {
                id: upcomingMouse
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openMatch(upcomingCard.modelData)
              }
            }
          }

          Text {
            visible: root.loading
            Layout.fillWidth: true
            text: "Refreshing VLR.gg..."
            color: root.dimText
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            font.italic: true
          }

          Text {
            Layout.fillWidth: true
            text: "Source: vlr.gg  |  Press R to refresh"
            color: root.dimmerText
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            opacity: 0.7
          }
        }

        QQC.ScrollBar.vertical: QQC.ScrollBar {
          policy: QQC.ScrollBar.AsNeeded
        }
      }
    }
  }

  IpcHandler {
    target: "cassian.vct-scoreline"

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function state(): string {
      return JSON.stringify({
        opened: root.opened,
        loading: root.loading,
        live: root.liveMatches,
        upcoming: root.upcomingMatches,
        error: root.errorText,
        lastUpdated: root.lastUpdated
      })
    }
  }
}
