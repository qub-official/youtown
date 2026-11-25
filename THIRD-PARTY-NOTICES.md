# Third-party notices

YouTown Player's own source code is released under the [MIT License](LICENSE).
The Windows installer also bundles the following components, which keep their own licenses:

| Component | Used for | License |
|---|---|---|
| [libVLC](https://www.videolan.org/vlc/libvlc.html) (VLC media player 3.0) | Audio and video playback | LGPL 2.1 or later (a copy ships as `vlc/COPYING.txt` in the install folder) |
| [Qt 6](https://www.qt.io/) / [PySide6](https://doc.qt.io/qtforpython/) | User interface | LGPL 3 |
| [python-vlc](https://github.com/oaubert/python-vlc) | Python bindings for libVLC | LGPL 2.1 or later |
| [Python](https://www.python.org/) | Runtime | PSF License |

These libraries are included as separate, unmodified dynamic libraries, so you can replace them with your own
builds. Their source code is available from the links above.

YouTown Player isn't affiliated with or endorsed by VideoLAN or The Qt Company.
