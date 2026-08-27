# VCT Scoreline

Omarchy bar widget for live top-tier Valorant Champions Tour scores and upcoming matches from [VLR.gg](https://www.vlr.gg/).

The widget includes regional VCT leagues, Masters, Champions, and LOCK//IN. It excludes Challengers, VCL, Ascension, Game Changers, academy, collegiate, and offseason events.

## Install

```sh
omarchy plugin add https://github.com/SeeSharpSi/omarchy-vct-scoreline.git --enable
omarchy bar move cassian.vct-scoreline --section right
```

## Usage

Click `VCT` in the bar to open the panel. The label turns red while a match is live. Press `R` or use the refresh button for an immediate update.

During a live map, the panel shows map score, series score, current map, round, and attacking side. The attacking team's map score is red. If regional matches overlap, all live top-tier matches are shown.

Click any live or upcoming match card to open its match page on VLR.gg.

The widget refreshes every 30 seconds while a match is live and every 120 seconds otherwise. Both intervals are configurable through Omarchy's plugin settings.

By default the bar icon is always visible, even when no match is live. To hide it when inactive, enable `hideWhenInactive` in `~/.config/omarchy/shell.json` (uses the per-widget `BarWidget.setting()` entry, no separate config file). When enabled, the icon collapses when no live match is present and only appears during live matches or when the grouped `omarchy.indicators` host is revealing inactive indicators (e.g. on hover).

Example bar layout entry in `~/.config/omarchy/shell.json`:

```json
{
  "bar": {
    "layout": {
      "center": [
        {
          "id": "cassian.vct-scoreline",
          "hideWhenInactive": true
        }
      ]
    }
  }
}
```

Set `hideWhenInactive` to `false` (or remove it) to always show the icon. The setting defaults to `false`.

## Remove

```sh
omarchy plugin remove cassian.vct-scoreline
```

## Development

Work on this checkout as a user-owned Omarchy plugin:

```sh
ln -s "$PWD" ~/.config/omarchy/plugins/cassian.vct-scoreline
omarchy-shell shell rescanPlugins
omarchy plugin enable cassian.vct-scoreline --section right
```

Omarchy reloads plugin code automatically when files inside its plugin directory change. A symlinked development checkout may require another `omarchy-shell shell rescanPlugins` after edits.

### Test

```sh
python3 -m unittest discover -s tests -v
python3 vlr.py
omarchy plugin validate .
qmllint -I "$OMARCHY_PATH/shell" Widget.qml
```

`vlr.py` uses only Python's standard library. VLR.gg has no supported public API for this data, so site markup changes can require parser updates.

## License

[MIT](LICENSE)
