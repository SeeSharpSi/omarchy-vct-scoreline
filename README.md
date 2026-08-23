# VCT Scoreline

Omarchy bar widget for live top-tier Valorant Champions Tour scores and upcoming matches from [VLR.gg](https://www.vlr.gg/).

The widget includes regional VCT leagues, Masters, Champions, and LOCK//IN. It excludes Challengers, VCL, Ascension, Game Changers, academy, collegiate, and offseason events.

## Install

Install this checkout as a user-owned Omarchy plugin:

```bash
ln -s "$PWD" ~/.config/omarchy/plugins/cassian.vct-scoreline
omarchy-shell shell rescanPlugins
omarchy plugin enable cassian.vct-scoreline --section right
```

Omarchy reloads plugin code automatically when files inside its plugin directory change. A symlinked development checkout may require another `omarchy-shell shell rescanPlugins` after edits.

## Usage

Click `VCT` in the bar to open the panel. The label turns red while a match is live. Press `R` or use the refresh button for an immediate update.

During a live map, the panel shows map score, series score, current map, round, and attacking side. The attacking team's map score is red. If regional matches overlap, all live top-tier matches are shown.

The widget refreshes every 30 seconds while a match is live and every 120 seconds otherwise. Both intervals are configurable through Omarchy's plugin settings.

## Test

```bash
python3 -m unittest discover -s tests -v
python3 vlr.py
omarchy plugin validate .
```

`vlr.py` uses only Python's standard library. VLR.gg has no supported public API for this data, so site markup changes can require parser updates.
