# ShowMaster Arena Creator

Build grandstands for **Planet Coaster 2** and use them in the game as working show rides:
guests walk in, take a seat, watch the show and leave again.

* **App** – a Windows program with a live 3D view. Six steps: shape, rows & seats, stairs & paths,
  railings, look, into the game. Languages: English, Deutsch, Français, Español, 中文, 日本語.
* **Blender add-on** – the same generator inside Blender, plus tools for your own tribune models.
* **Guest Spawner** (optional) – a "+500 guests" button in the park, for testing.

Everything in this repository is open source (GPL-3.0). The downloads on the
[Releases](../../releases) page are built from this source by GitHub Actions – see [VERIFY.md](VERIFY.md).

## Install (app)

Requirements: Windows 10/11, Planet Coaster 2 with the **Silver Screen DLC**.
In the game the ride uses **ACSE** and **ForgeUtils** (the Guest Spawner needs ForgeUtils).

1. Download `ShowMaster_Arena_Creator_Setup_<version>.exe` from [Releases](../../releases) and run it.
   No admin rights needed; it installs into your user folder.
2. Start *ShowMaster Arena Creator* from the Start menu.
3. Build your grandstand, close the game, click **Save and install into the game** in the last step.
4. Start the game. The grandstand is in the ride menu as **"Show Arena &lt;seats&gt;"**.

A portable zip (no installation) is on the Releases page as well.

## What the program does on your PC

| | |
|---|---|
| Writes | `…\Planet Coaster 2\Win64\ovldata\Mod_TB_<name>\` (one folder per grandstand), `Mod_GuestSpawner\` only when you install it under Extras |
| Deletes | only `Mod_TB_…` folders it made itself (they carry a `.pc2_tribune_builder` marker file) |
| Reads | the cinema ride `FR_Cinema.ovl` of the Silver Screen DLC (as a template, nothing of it is in this repository) |
| Keeps | your saved grandstands and settings in `%APPDATA%\ShowMaster Arena Creator\` (or the Blender add-on's library, if you use the add-on) |
| Network | none. The program does not connect to the internet |
| Local server | the user interface talks to the program over `127.0.0.1` only; nothing is reachable from outside your PC |

## Run from source

```
python -m pip install -r packaging/requirements-build.txt
python tools/assemble_app.py build/app <path to cobra-tools>
python build/app/server.py
```

Build the installer yourself (Windows, Python 3.12, [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```
py -3.12 packaging/build_exe.py
```

## Project layout

| Folder | |
|---|---|
| `blender_addon/pc2_tribune_builder/` | Blender add-on; `core/` is the generator, navmesh check and mod builder used by both add-on and app |
| `app/` | the app: local server (`server.py`) and user interface (`web/`, plain HTML/JS, own WebGL viewer) |
| `guestspawner/` | Guest Spawner mod source (Lua + JS) |
| `packaging/` | Windows program (PyInstaller) and installer (Inno Setup) |
| `tools/` | assembling the app, building the Guest Spawner |
| `tests/` | generator checks, run on every push |

## License

GPL-3.0 – see [LICENSE](LICENSE). Third-party parts: [THIRD_PARTY.md](THIRD_PARTY.md).
Made by ImmersiveWerks, with the help of Claude (Anthropic).
Not affiliated with Frontier Developments. Planet Coaster is a trademark of Frontier Developments plc.
