# Glean

Keep the grain. Leave the rest.

Glean is a desktop app for sermons and talks. Drop a video. It transcribes the talk on that computer, keeps the times on each line, and pulls the hardest punches — the lines worth clipping — along with any Scripture the speaker actually cited.

Nothing is uploaded. The transcript, the notes, and the speech model stay on the machine that runs it.

## Download for Windows

Get the latest build from [Releases](https://github.com/cityinflames/glean/releases/latest).

1. Download `Glean-windows.zip`.
2. Unzip it somewhere you keep programs.
3. Double-click `Glean.exe`.

The first sermon downloads a speech model and can take as long as the recording. After that, the model stays on that PC.

## Keep working on it

This folder is the workshop. Packaging a download does not freeze the program. Change the code here, then build again when you want other people to have the new version.

```
Run-Glean.bat
```

opens the workshop copy on this computer.

```
.\.venv\Scripts\python.exe -m PyInstaller glean.spec
```

writes a fresh `dist\Glean` folder you can zip for a release.
