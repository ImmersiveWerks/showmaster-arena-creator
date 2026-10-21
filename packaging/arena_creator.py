"""ShowMaster Arena Creator - program entry for the Windows .exe (PyInstaller).

The app code (app/) and cobra-tools stay plain folders next to the exe, so cobra-tools can load its formats
and data at run time. The program makes no internet connections. The window is a native window (Edge WebView2 through pywebview);
without WebView2 the app opens in an Edge/Chrome app window instead.
"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
BASE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(BASE, "app")
COBRA = os.path.join(BASE, "cobra-tools")
if os.path.isdir(os.path.join(COBRA, "generated")):
    os.environ.setdefault("TB_COBRA", COBRA)
sys.path.insert(0, APP)

# third-party packages used by the app and cobra-tools (imported here so PyInstaller bundles them)
if os.environ.get("TB_BUNDLE_ANALYSIS_ONLY"):
    import bitarray  # noqa: F401
    import imageio  # noqa: F401
    import imageio.v3  # noqa: F401
    import numpy  # noqa: F401
    import PIL.Image  # noqa: F401
    import PIL.ImageDraw  # noqa: F401
    import PIL.ImageFilter  # noqa: F401
    import tkinter  # noqa: F401
    import webview  # noqa: F401


def control_window(url, server):
    """fallback when there is no WebView2: a small window to reopen the app window or quit"""
    server.open_window(url)
    import tkinter
    win = tkinter.Tk()
    win.title("ShowMaster Arena Creator")
    win.geometry("360x130")
    win.resizable(False, False)
    tkinter.Label(win, text="ShowMaster Arena Creator").pack(pady=(16, 8))
    row = tkinter.Frame(win)
    row.pack()
    tkinter.Button(row, text="Open window / Fenster öffnen", command=lambda: server.open_window(url)).pack(side="left", padx=6)
    tkinter.Button(row, text="Quit / Beenden", command=lambda: os._exit(0)).pack(side="left", padx=6)
    win.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    win.mainloop()


def main():
    import server
    url = server.start(window=False)
    try:
        import webview
        webview.create_window("ShowMaster Arena Creator", url, width=1500, height=920, min_size=(1000, 640),
                              text_select=True)
        webview.start(private_mode=False)
    except Exception:
        control_window(url, server)
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ShowMaster Arena Creator", "error.log")
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror("ShowMaster Arena Creator", "%s\n\n%s" % (e, log))
        except Exception:
            pass
        os._exit(1)
