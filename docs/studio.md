# Rescript Studio

Rescript Studio is the drag-and-drop app. Start it with `bin/rescript app` (see [Use](../README.md#use) in the README).

## The start screen

Drop a screen recording onto the window, pick a saved voice if you have one, and choose whether to remove the mouse
cursor. While it runs, five cards (Transcribe, Rewrite, Re-voice, Retime, Check), each with its character, go from
Waiting to Working to Done.

## The result screen

When it's done you get the original and the
polished video side by side, the stats (length, words, long pauses removed, voice check, retakes), and the script. Click a
line to hear it, edit it or ask for a change, and only that line is redone. It can also save your voice for next
time and remove the mouse cursor. Recordings are copied to `~/Movies/Rescript/`, with the polished versions next to
them. The app runs the same `bin/rescript` commands as the terminal, and its server listens on this Mac only.

<p align="center">
  <img src="images/app-3-result.png" width="1280" alt="Rescript Studio screenshot: Before and After players, recording statistics, and a line-by-line script.">
</p>

The screenshot shows the golf talk from the demo video, which went from 1:33 to 0:36 (61% shorter). Other recordings will shorten by different amounts.

## Fix one line: Edit or Ask for a change

<img src="images/app-4-fix-a-line.png" width="1280" alt="Rescript Studio screenshot showing an Ask for a change field containing say it more simply, with Change and re-speak and Cancel controls.">

Only the selected line is spoken again; the video is rendered again from the saved work, reusing everything else.
