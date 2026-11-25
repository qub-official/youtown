"""libVLC playback engine: the same decoders VLC uses, so it plays whatever VLC plays."""
import os
import sys
import winreg
from pathlib import Path


def _find_vlc_dir():
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [here / "vlc", Path(sys.executable).parent / "vlc"]
    for sub in (r"SOFTWARE\VideoLAN\VLC", r"SOFTWARE\WOW6432Node\VideoLAN\VLC"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as k:
                candidates.append(Path(winreg.QueryValueEx(k, "InstallDir")[0]))
        except OSError:
            pass
    candidates.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "VideoLAN" / "VLC")
    for c in candidates:
        if (c / "libvlc.dll").exists():
            return c
    return None


VLC_DIR = _find_vlc_dir()
if VLC_DIR:
    os.add_dll_directory(str(VLC_DIR))
    os.environ["PATH"] = str(VLC_DIR) + os.pathsep + os.environ.get("PATH", "")
    os.environ["PYTHON_VLC_LIB_PATH"] = str(VLC_DIR / "libvlc.dll")
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(VLC_DIR / "plugins")
    os.environ["VLC_PLUGIN_PATH"] = str(VLC_DIR / "plugins")

try:
    import vlc  # noqa: E402
except Exception:  # VLC missing or wrong architecture
    vlc = None

ASPECTS = ["Default", "16:9", "4:3", "1:1", "16:10", "2.21:1", "2.35:1", "2.39:1", "5:4"]
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0]


def _s(b):
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)


class Engine:
    def __init__(self, hwnd: int):
        if vlc is None:
            raise RuntimeError("VLC engine not found. Install VLC (64-bit) from videolan.org.")
        self.instance = vlc.Instance([
            "--no-video-title-show", "--quiet", "--ignore-config", "--no-osd",
            "--no-snapshot-preview", "--audio-time-stretch",
        ])
        self.mp = self.instance.media_player_new()
        self.mp.set_hwnd(hwnd)
        self.mp.video_set_mouse_input(False)
        self.mp.video_set_key_input(False)
        self.media = None
        self._eq = None
        self.version = _s(vlc.libvlc_get_version())

    # --- media
    def open(self, path: str, is_url=False):
        self.mp.stop()
        self.media = self.instance.media_new(path) if is_url else self.instance.media_new_path(path)
        self.mp.set_media(self.media)
        try:
            self.media.parse_with_options(vlc.MediaParseFlag.local | vlc.MediaParseFlag.fetch_local, 0)
        except Exception:
            pass

    def play(self):
        self.mp.play()

    def pause(self):
        self.mp.set_pause(1)

    def resume(self):
        self.mp.set_pause(0)

    def toggle(self):
        if self.state() in ("ended", "stopped", "error"):
            self.mp.stop()
            self.mp.play()
        else:
            self.mp.pause()

    def stop(self):
        self.mp.stop()

    def state(self):
        st = self.mp.get_state()
        return {
            vlc.State.Playing: "playing", vlc.State.Paused: "paused", vlc.State.Ended: "ended",
            vlc.State.Error: "error", vlc.State.Stopped: "stopped", vlc.State.Opening: "opening",
            vlc.State.Buffering: "buffering",
        }.get(st, "idle")

    def is_playing(self):
        return bool(self.mp.is_playing())

    # --- time
    def time(self):
        return max(0, self.mp.get_time())

    def length(self):
        return max(0, self.mp.get_length())

    def set_time(self, ms):
        self.mp.set_time(int(max(0, ms)))

    def seekable(self):
        return bool(self.mp.is_seekable())

    def next_frame(self):
        self.mp.next_frame()

    # --- audio
    def set_volume(self, v):
        self.mp.audio_set_volume(int(v))

    def set_mute(self, m):
        self.mp.audio_set_mute(bool(m))

    def set_rate(self, r):
        self.mp.set_rate(float(r))

    def audio_tracks(self):
        return [(i, _s(n)) for i, n in (self.mp.audio_get_track_description() or [])]

    def audio_track(self):
        return self.mp.audio_get_track()

    def set_audio_track(self, i):
        self.mp.audio_set_track(i)

    def audio_delay(self):
        return self.mp.audio_get_delay() // 1000

    def set_audio_delay(self, ms):
        self.mp.audio_set_delay(int(ms * 1000))

    def eq_presets(self):
        n = vlc.libvlc_audio_equalizer_get_preset_count()
        return [_s(vlc.libvlc_audio_equalizer_get_preset_name(i)) for i in range(n)]

    def set_eq_preset(self, index):
        if index is None or index < 0:
            self._eq = None
            self.mp.set_equalizer(None)
        else:
            self._eq = vlc.libvlc_audio_equalizer_new_from_preset(index)
            self.mp.set_equalizer(self._eq)

    # --- video / subtitles
    def has_video(self):
        return self.mp.has_vout() > 0

    def set_aspect(self, a):
        self.mp.video_set_aspect_ratio(None if a in (None, "Default") else a)

    def snapshot(self, path):
        return self.mp.video_take_snapshot(0, str(path), 0, 0) == 0

    def sub_tracks(self):
        return [(i, _s(n)) for i, n in (self.mp.video_get_spu_description() or [])]

    def sub_track(self):
        return self.mp.video_get_spu()

    def set_sub_track(self, i):
        self.mp.video_set_spu(i)

    def add_subtitle(self, path):
        from PySide6.QtCore import QUrl
        return self.mp.add_slave(vlc.MediaSlaveType.subtitle, QUrl.fromLocalFile(path).toString(), True) == 0

    def sub_delay(self):
        return self.mp.video_get_spu_delay() // 1000

    def set_sub_delay(self, ms):
        self.mp.video_set_spu_delay(int(ms * 1000))

    # --- metadata
    def meta(self):
        if not self.media:
            return {}
        out = {}
        for key, m in (("title", vlc.Meta.Title), ("artist", vlc.Meta.Artist), ("album", vlc.Meta.Album),
                       ("art", vlc.Meta.ArtworkURL), ("now", vlc.Meta.NowPlaying)):
            try:
                v = self.media.get_meta(m)
            except Exception:
                v = None
            if v:
                out[key] = _s(v)
        return out

    def release(self):
        try:
            self.mp.stop()
            self.mp.release()
            self.instance.release()
        except Exception:
            pass
