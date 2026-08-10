# coding: utf-8
import hashlib
import random
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PyQt5.QtCore import QByteArray, QObject, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtNetwork import QNetworkRequest

from app.common.signal_bus import signalBus
from app.common.setting import CONFIG_FOLDER
from app.components.play_bar import PlayBar, PlayBarSongInfo, PlaybackMode
from app.models.music import MusicItem, PlayInfo
from app.services.remote_asset import get_remote_asset
from app.services.providers import get_provider

try:
    from colorthief import ColorThief
except ImportError:
    ColorThief = None

DEFAULT_VOLUME = 28
COVER_TIMEOUT = 12
MEDIA_TIMEOUT = 45
MEDIA_CHUNK_SIZE = 1024 * 256
MEDIA_CACHE_DIR = CONFIG_FOLDER / "media_cache"
LOCAL_PREPARE_PROVIDERS = {"aiting", "livepoo", "qqmp3"}
LOCAL_PREPARE_EXTENSIONS = {"m4a"}
LOCAL_PREPARE_HOST_KEYWORDS = ("kuwo.cn", "5bb3.com")
LOCAL_AUDIO_EXTENSIONS = {"aac", "flac", "m4a", "mp3", "ogg", "wav", "wma"}
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive",
}


def _duration_to_seconds(duration: str | None) -> int:
    if not duration:
        return 0
    parts = duration.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return 0
    return 0


class MediaPrepareThread(QThread):
    prepared = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(
        self,
        index: int,
        item: MusicItem,
        extra_overrides: dict[str, Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.item = item
        self.extra_overrides = extra_overrides or {}

    def run(self) -> None:
        try:
            provider = get_provider(self.item.provider)
            extra = dict(self.item.extra)
            extra.update(self.extra_overrides)
            if self.item.provider == "netease" and not extra.get("level"):
                extra["level"] = "exhigh"
            if self.item.provider in {"qq-official", "kugou"}:
                extra["usage"] = "playback"
            if self.item.cover:
                extra["cover"] = self.item.cover
            play_info = provider.get_play_info(self.item.id, extra)
            play_info = self._prepare_play_info(play_info)
            if self.isInterruptionRequested():
                return
            self.prepared.emit(self.index, play_info)
        except Exception as error:
            self.failed.emit(self.index, str(error))

    def _prepare_play_info(self, play_info: PlayInfo) -> PlayInfo:
        if not self._should_prepare_local(play_info):
            return play_info

        media_path = self._download_media(play_info)
        return PlayInfo(
            url=media_path,
            type=play_info.type,
            bitrate=play_info.bitrate,
            cover=play_info.cover,
        )

    def _should_prepare_local(self, play_info: PlayInfo) -> bool:
        if self.item.provider not in LOCAL_PREPARE_PROVIDERS:
            return False
        if not play_info.url.startswith("http"):
            return False

        extension = self._safe_suffix(play_info.type) or self._suffix_from_url(play_info.url)
        if extension in LOCAL_PREPARE_EXTENSIONS:
            return True

        host = urlparse(play_info.url).netloc.lower()
        return self.item.provider == "qqmp3" and any(keyword in host for keyword in LOCAL_PREPARE_HOST_KEYWORDS)

    def _download_media(self, play_info: PlayInfo) -> str:
        MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_stem = self._cache_stem(play_info.url)
        cached_file = self._find_cached_media(cache_stem)
        if cached_file:
            return str(cached_file)

        suffix = self._safe_suffix(play_info.type) or self._suffix_from_url(play_info.url) or "mp3"
        temp_file = MEDIA_CACHE_DIR / f"{cache_stem}.{suffix}.tmp"
        cache_file = MEDIA_CACHE_DIR / f"{cache_stem}.{suffix}"
        with requests.get(play_info.url, headers=self._media_headers(play_info), timeout=MEDIA_TIMEOUT, stream=True) as response:
            response.raise_for_status()
            self._write_media_file(response, temp_file)

        if self.isInterruptionRequested():
            temp_file.unlink(missing_ok=True)
            raise InterruptedError("Media preparation interrupted")
        temp_file.replace(cache_file)
        return str(cache_file)

    def _write_media_file(self, response: requests.Response, temp_file: Path) -> None:
        with temp_file.open("wb") as file:
            for chunk in response.iter_content(chunk_size=MEDIA_CHUNK_SIZE):
                if self.isInterruptionRequested():
                    raise InterruptedError("Media download interrupted")
                if chunk:
                    file.write(chunk)

    def _media_headers(self, play_info: PlayInfo) -> dict[str, str]:
        return {**REQUEST_HEADERS, **play_info.headers}

    def _cache_stem(self, url: str) -> str:
        source = f"{self.item.provider}:{self.item.id}:{url}"
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
        return f"{self.item.provider}_{self.item.id}_{digest}"

    def _find_cached_media(self, cache_stem: str) -> Path | None:
        for extension in LOCAL_AUDIO_EXTENSIONS:
            cache_file = MEDIA_CACHE_DIR / f"{cache_stem}.{extension}"
            if cache_file.exists() and cache_file.stat().st_size > 0:
                return cache_file
        return None

    def _suffix_from_url(self, url: str) -> str:
        path = urlparse(url).path
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return self._safe_suffix(suffix)

    def _safe_suffix(self, value: str | None) -> str:
        suffix = str(value or "").strip().lower().lstrip(".")
        if suffix in LOCAL_AUDIO_EXTENSIONS:
            return suffix
        return ""


class CoverThemeThread(QThread):
    loaded = pyqtSignal(bytes, object)
    failed = pyqtSignal()

    def __init__(self, cover_url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cover_url = cover_url

    def run(self) -> None:
        if not self.cover_url.startswith("http"):
            self.failed.emit()
            return

        try:
            if self.isInterruptionRequested():
                return
            response = get_remote_asset(self.cover_url, headers=REQUEST_HEADERS, timeout=COVER_TIMEOUT)
            response.raise_for_status()
            image_bytes = response.content
            if self.isInterruptionRequested():
                return
            color = self._extract_color(image_bytes)
            if self.isInterruptionRequested():
                return
            self.loaded.emit(image_bytes, color)
        except requests.RequestException:
            self.failed.emit()

    def _extract_color(self, image_bytes: bytes) -> QColor:
        if ColorThief is None:
            return QColor()
        red, green, blue = ColorThief(BytesIO(image_bytes)).get_color(quality=10)
        return QColor(red, green, blue)


class PlaybackService(QObject):
    """Global playback state and media controller."""

    def __init__(self, play_bar: PlayBar, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.play_bar = play_bar
        self.player = QMediaPlayer(self)
        self.playlist: list[MusicItem] = []
        self.current_index = -1
        self.mode = PlaybackMode.LIST_LOOP
        self.resolve_thread: MediaPrepareThread | None = None
        self.cover_thread: CoverThemeThread | None = None
        self.has_started_current_media = False
        self.has_handled_current_error = False
        self.current_media_path = ""
        self.current_cover_url = ""

        self._init_player()
        self._connect_signals()
        self.play_bar.clear_song()

    def set_playlist(self, items: list[MusicItem], start_index: int) -> None:
        if not items:
            return
        self.playlist = list(items)
        self.play_index(start_index)

    def play_index(self, index: int) -> None:
        if not 0 <= index < len(self.playlist):
            return

        self.current_index = index
        self.has_started_current_media = False
        self.has_handled_current_error = False
        self.current_media_path = ""
        self.current_cover_url = ""
        item = self.playlist[index]
        self._set_pending_song(item)
        self._resolve_play_info(index, item)

    def toggle_play(self) -> None:
        if self.player.mediaStatus() == QMediaPlayer.NoMedia:
            self.play_index(max(self.current_index, 0))
            return

        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play_previous(self) -> None:
        if not self.playlist:
            return
        self.play_index((self.current_index - 1) % len(self.playlist))

    def play_next(self) -> None:
        next_index = self._next_index()
        if next_index is not None:
            self.play_index(next_index)

    def set_mode(self, mode: PlaybackMode) -> None:
        self.mode = mode
        self.play_bar.set_mode(mode)

    def set_volume(self, volume: int) -> None:
        fixed_volume = min(max(volume, 0), 100)
        self.player.setMuted(fixed_volume <= 0)
        self.player.setVolume(fixed_volume)
        self.play_bar.set_volume(fixed_volume)

    def toggle_mute(self) -> None:
        self.player.setMuted(not self.player.isMuted())
        self.play_bar.set_muted(self.player.isMuted())

    def _init_player(self) -> None:
        self.player.setVolume(DEFAULT_VOLUME)
        self.play_bar.set_volume(DEFAULT_VOLUME)

    def _connect_signals(self) -> None:
        signalBus.playPlaylistRequested.connect(self.set_playlist)
        signalBus.playbackToggleRequested.connect(self.toggle_play)
        signalBus.playbackPreviousRequested.connect(self.play_previous)
        signalBus.playbackNextRequested.connect(self.play_next)
        signalBus.playbackSeekRequested.connect(self.player.setPosition)
        signalBus.playbackVolumeChanged.connect(self.set_volume)
        signalBus.playbackMuteRequested.connect(self.toggle_mute)
        signalBus.playbackModeChanged.connect(self.set_mode)
        self.play_bar.playPauseRequested.connect(self.toggle_play)
        self.play_bar.previousRequested.connect(self.play_previous)
        self.play_bar.nextRequested.connect(self.play_next)
        self.play_bar.modeChanged.connect(self.set_mode)
        self.play_bar.volumeChanged.connect(self.set_volume)
        self.play_bar.muteRequested.connect(self.toggle_mute)
        self.play_bar.positionChanged.connect(self.player.setPosition)
        self.play_bar.songCardClicked.connect(signalBus.switchToPlayingInterfaceRequested)
        self.player.positionChanged.connect(self.play_bar.set_position)
        self.player.positionChanged.connect(lambda position: signalBus.playbackPositionChanged.emit(int(position)))
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.stateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.error.connect(self._on_player_error)

    def _set_pending_song(self, item: MusicItem) -> None:
        self.play_bar.set_song(
            PlayBarSongInfo(
                title=item.title,
                singer=item.artist,
                album=item.album or "未知专辑",
                duration=_duration_to_seconds(item.duration),
                cover=item.cover or "",
            )
        )

    def _resolve_play_info(
        self,
        index: int,
        item: MusicItem,
        extra_overrides: dict[str, Any] | None = None,
    ) -> None:
        if self.resolve_thread is not None and self.resolve_thread.isRunning():
            self.resolve_thread.requestInterruption()

        thread = MediaPrepareThread(index, item, extra_overrides, self)
        thread.prepared.connect(self._on_media_prepared)
        thread.failed.connect(self._on_play_info_failed)
        thread.finished.connect(self._on_resolve_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self.resolve_thread = thread
        thread.start()

    def _on_media_prepared(self, index: int, play_info: PlayInfo) -> None:
        if index != self.current_index:
            return

        self.current_media_path = play_info.url
        self.player.setMedia(self._media_content(play_info))
        self.player.play()
        signalBus.playbackTrackChanged.emit(self.playlist[index], index)
        self._load_cover(play_info.cover or self.playlist[index].cover or "")

    def _on_play_info_failed(self, index: int, message: str) -> None:
        if index == self.current_index:
            signalBus.playbackError.emit(message or "获取播放链接失败")

    def _load_cover(self, cover_url: str) -> None:
        if not cover_url:
            self.play_bar.animate_color(self.play_bar.default_color())
            self.play_bar.set_default_cover()
            return
        if cover_url == self.current_cover_url:
            return
        self.current_cover_url = cover_url
        if self.cover_thread is not None and self.cover_thread.isRunning():
            self.cover_thread.requestInterruption()

        thread = CoverThemeThread(cover_url, self)
        thread.loaded.connect(self._on_cover_loaded)
        thread.finished.connect(self._on_cover_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self.cover_thread = thread
        thread.start()

    def _on_cover_loaded(self, image_bytes: bytes, color: Any) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        self.play_bar.set_cover_pixmap(pixmap)
        signalBus.playbackCoverChanged.emit(pixmap, color)
        if isinstance(color, QColor) and color.isValid():
            self.play_bar.animate_color(color)

    def _on_duration_changed(self, duration: int) -> None:
        if duration > 0:
            self.play_bar.progress_bar.set_total_time(duration // 1000)
            signalBus.playbackDurationChanged.emit(duration)

    def _on_state_changed(self, state: QMediaPlayer.State) -> None:
        if state == QMediaPlayer.PlayingState:
            self.has_started_current_media = True
        is_playing = state == QMediaPlayer.PlayingState
        self.play_bar.set_playing(is_playing)
        signalBus.playbackStateChanged.emit(is_playing)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.InvalidMedia:
            if self.has_handled_current_error:
                return
            self.has_handled_current_error = True
            signalBus.playbackError.emit("当前音频无法播放，请尝试下一首")
            return
        if status == QMediaPlayer.EndOfMedia:
            if not self._is_real_media_end():
                return
            if self.mode == PlaybackMode.SINGLE_LOOP:
                self.play_index(self.current_index)
            else:
                self.play_next()

    def _on_player_error(self, error: QMediaPlayer.Error) -> None:
        if error != QMediaPlayer.NoError:
            if self._should_ignore_remote_resource_error(error):
                return
            if self.has_handled_current_error:
                return
            self.has_handled_current_error = True
            signalBus.playbackError.emit(self.player.errorString() or "媒体播放失败")

    def _on_resolve_thread_finished(self) -> None:
        if self.sender() is self.resolve_thread:
            self.resolve_thread = None

    def _on_cover_thread_finished(self) -> None:
        if self.sender() is self.cover_thread:
            self.cover_thread = None

    def _is_real_media_end(self) -> bool:
        duration = self.player.duration()
        if not self.has_started_current_media or duration <= 0:
            return False
        return self.player.position() >= duration - 1000

    def _media_content(self, play_info: PlayInfo) -> QMediaContent:
        if not play_info.url.startswith("http"):
            return QMediaContent(QUrl.fromLocalFile(play_info.url))
        if not play_info.headers:
            return QMediaContent(QUrl(play_info.url))

        request = QNetworkRequest(QUrl(play_info.url))
        for name, value in play_info.headers.items():
            request.setRawHeader(QByteArray(name.encode("utf-8")), QByteArray(value.encode("utf-8")))
        return QMediaContent(request)

    def _should_ignore_remote_resource_error(self, error: QMediaPlayer.Error) -> bool:
        return self.current_media_path.startswith("http") and error == QMediaPlayer.ResourceError

    def _next_index(self) -> int | None:
        if not self.playlist:
            return None
        if self.mode == PlaybackMode.RANDOM and len(self.playlist) > 1:
            choices = [index for index in range(len(self.playlist)) if index != self.current_index]
            return random.choice(choices)
        return (self.current_index + 1) % len(self.playlist)
