"""File types. Video/audio/playlist lists mirror VLC's own extension lists."""

VIDEO = set("""
3g2 3gp 3gp2 3gpp amv asf avi bik crf dav divx drc dv dvr-ms evo f4v flv gvi gxf m1v m2v m2t m2ts
m4v mkv mov mp2v mp4 mp4v mpe mpeg mpeg1 mpeg2 mpeg4 mpg mpv2 mts mtv mxf mxg nsv nuv ogm ogv ogx
ps rec rm rmvb rpl thp tod tp ts tts vob vro webm wm wmv wtv xesc
""".split())

AUDIO = set("""
3ga 669 a52 aac ac3 adt adts aif aifc aiff amb amr aob ape au awb caf dts dsf dff flac it kar m4a
m4b m4p m5p mid midi mka mlp mod mpa mp1 mp2 mp3 mpc mpga mus oga ogg oma opus qcp ra rmi s3m sid
spx tak thd tta voc vqf w64 wav weba wma wv xa xm
""".split())

IMAGE = set("jpg jpeg jpe jfif png gif webp bmp dib tif tiff ico svg avif heic heif tga".split())

PLAYLIST = set("asx b4s cue m3u m3u8 pls ram sdp vlc xspf wax wvx".split())
DISC = {"iso"}
SUBTITLE = set("srt ass ssa sub idx vtt smi sbv ttml usf jss psb mpl2 aqt pjs rt stl dks".split())

# Extensions that are also common non-media files (TypeScript, go.mod, PostScript...).
# During library scans these only count when the file is big enough to be real media.
AMBIGUOUS_MIN_SIZE = {
    "ts": 512_000, "tp": 512_000, "ps": 512_000, "rec": 512_000, "dav": 512_000, "crf": 512_000,
    "mod": 16_000, "it": 16_000, "mus": 16_000, "au": 16_000, "xa": 16_000, "sid": 4_000,
}

LIBRARY = VIDEO | AUDIO | IMAGE
OPENABLE = LIBRARY | PLAYLIST | DISC

# Offered to Windows "Default apps" (ambiguous developer extensions are left out on purpose).
ASSOC = sorted((VIDEO | AUDIO | PLAYLIST | (IMAGE - {"svg", "ico"})) - set(AMBIGUOUS_MIN_SIZE))


def ext_of(path: str) -> str:
    i = path.rfind(".")
    return path[i + 1:].lower() if i > max(path.rfind("\\"), path.rfind("/")) else ""


def type_of(path: str) -> str | None:
    e = ext_of(path)
    if e in VIDEO and e not in AUDIO:
        return "video"
    if e in AUDIO:
        return "audio"
    if e in IMAGE:
        return "image"
    if e in DISC:
        return "video"
    return None
