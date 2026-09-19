"""用本机 PotPlayer 打开已入库视频.

``resolve`` 只返回 ``FilePlaybackTarget``, 供网页内播放器取流. 启动 PotPlayer 走 ``probe``
声明的 ``open`` 操作, 由用户点按钮触发, 与 Range / ``cache_ttl`` 解耦.

仅适用于 Amane 与 PotPlayer 运行在同一台 Windows 本机的场景 (桌面版 / 本机服务).
Docker 或远程服务器上的进程无法打开用户桌面上的 PotPlayer.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import override

from pydantic import BaseModel, ConfigDict, Field

from amane.plugin import (
    FailureReason,
    FilePlaybackTarget,
    PlaybackAction,
    PlaybackMediaFile,
    PlaybackOffer,
    PlaybackPlugin,
    PlaybackProvider,
    PlaybackQuery,
    PluginContext,
    SourceCapability,
    SourceDescriptor,
    SourceError,
)

PLUGIN_ID = "local.potplayer"
_OPEN_ACTION_ID = "open"
_OPEN_ACTION = PlaybackAction(id=_OPEN_ACTION_ID, label="用 PotPlayer 打开")
_RESOLVE_CACHE_TTL = 120.0

_DEFAULT_EXECUTABLES = (
    Path(r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe"),
    Path(r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini.exe"),
    Path(r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini64.exe"),
    Path(r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini.exe"),
)

_WHICH_NAMES = (
    "PotPlayerMini64.exe",
    "PotPlayerMini.exe",
    "PotPlayer64.exe",
    "PotPlayer.exe",
)


class PotPlayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executable: str = Field(
        default="",
        description="PotPlayer 可执行文件路径; 留空则自动探测常见安装位置与 PATH",
    )
    args: str = Field(
        default="",
        description="附加命令行参数, 按 Windows 规则用空格分隔",
    )
    ignore_strm: bool = Field(
        default=True,
        description="忽略 .strm 指针文件, 不列出也不用 PotPlayer 打开",
    )


def _file_key(media: PlaybackMediaFile) -> str:
    return f"f{media.id}"


def _display_name(media: PlaybackMediaFile) -> str:
    name = Path(media.path).name
    return name or media.path


def _is_strm(media: PlaybackMediaFile) -> bool:
    return Path(media.path).suffix.casefold() == ".strm"


def _content_type_for(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith(("video/", "audio/")):
        return guessed
    return "video/mp4"


def _path_stat(path: str) -> tuple[bool, int]:
    target = Path(path)
    try:
        if not target.is_file():
            return False, 0
        return True, target.stat().st_size
    except OSError:
        return False, 0


def _find_executable(configured: str) -> Path | None:
    if configured.strip():
        candidate = Path(configured.strip())
        if candidate.is_file():
            return candidate
        return None

    for name in _WHICH_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    for candidate in _DEFAULT_EXECUTABLES:
        if candidate.is_file():
            return candidate
    return None


def _parse_extra_args(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    return shlex.split(text, posix=False)


def _launch_potplayer(executable: Path, media_path: Path, extra_args: list[str]) -> None:
    command = [str(executable), str(media_path), *extra_args]
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # 脱离 Amane 进程树, 避免随服务退出.
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        kwargs["cwd"] = str(executable.parent)
    # 可执行路径与媒体路径分别来自配置 / 已索引文件, 不经过 shell.
    subprocess.Popen(command, **kwargs)


class PotPlayerProvider(PlaybackProvider):
    def __init__(self, config: PotPlayerConfig) -> None:
        self._config = config

    def _require_windows(self) -> None:
        if sys.platform != "win32":
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail="PotPlayer 插件仅支持 Windows 本机",
            )

    def _resolve_executable(self) -> Path:
        self._require_windows()
        found = _find_executable(self._config.executable)
        if found is None:
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail="未找到 PotPlayer, 请在插件配置中填写可执行文件路径",
            )
        return found

    def _candidate_files(self, query: PlaybackQuery) -> tuple[PlaybackMediaFile, ...]:
        if not self._config.ignore_strm:
            return query.files
        return tuple(media for media in query.files if not _is_strm(media))

    def _pick_file(self, query: PlaybackQuery) -> PlaybackMediaFile:
        candidates = self._candidate_files(query)
        if not candidates:
            if query.files and self._config.ignore_strm:
                raise SourceError(
                    FailureReason.NO_USABLE_METADATA,
                    detail="该条目只有 .strm 文件 (已按设置忽略)",
                )
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail="该条目没有已索引的本地文件",
            )

        if query.selected_key is None:
            return candidates[0]

        for media in candidates:
            if _file_key(media) == query.selected_key:
                return media

        # 选中项是被忽略的 .strm, 或已不在索引中.
        if self._config.ignore_strm:
            for media in query.files:
                if _file_key(media) == query.selected_key and _is_strm(media):
                    raise SourceError(
                        FailureReason.NO_USABLE_METADATA,
                        detail="已忽略 .strm 文件",
                    )
        raise SourceError(
            FailureReason.NO_USABLE_METADATA,
            detail="所选文件不在该条目的索引中",
        )

    def _require_media_file(self, media: PlaybackMediaFile) -> Path:
        name = _display_name(media)
        exists, size = _path_stat(media.path)
        if not exists:
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail=f"文件不存在: {name}",
            )
        if size == 0:
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail=f"文件为空: {name}",
            )
        return Path(media.path)

    @override
    async def probe(self, query: PlaybackQuery) -> tuple[PlaybackOffer, ...]:
        candidates = self._candidate_files(query)
        if not candidates:
            if query.files and self._config.ignore_strm:
                raise SourceError(
                    FailureReason.NO_USABLE_METADATA,
                    detail="该条目只有 .strm 文件 (已按设置忽略)",
                )
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail="该条目没有已索引的本地文件",
            )

        exe_error: str | None = None
        try:
            await asyncio.to_thread(self._resolve_executable)
        except SourceError as exc:
            exe_error = exc.detail or "PotPlayer 不可用"

        offers: list[PlaybackOffer] = []
        for media in candidates:
            name = _display_name(media)
            exists, size = await asyncio.to_thread(_path_stat, media.path)
            unavailable: str | None = None
            if exe_error is not None:
                unavailable = exe_error
            elif not exists:
                unavailable = f"文件不存在: {name}"
            elif size == 0 or media.size == 0:
                unavailable = f"文件为空: {name}"

            offers.append(
                PlaybackOffer(
                    key=_file_key(media),
                    name=name,
                    content_type=_content_type_for(media.path),
                    seekable=True,
                    unavailable=unavailable,
                    actions=() if unavailable is not None else (_OPEN_ACTION,),
                )
            )
        return tuple(offers)

    @override
    async def resolve(self, query: PlaybackQuery) -> FilePlaybackTarget | None:
        media = self._pick_file(query)
        media_path = await asyncio.to_thread(self._require_media_file, media)
        return FilePlaybackTarget(
            path=media_path,
            content_type=_content_type_for(media.path),
            cache_ttl=_RESOLVE_CACHE_TTL,
        )

    @override
    async def action(self, query: PlaybackQuery, action_id: str) -> None:
        if action_id != _OPEN_ACTION_ID:
            raise SourceError(FailureReason.NO_USABLE_METADATA, detail="不支持此操作")

        media = self._pick_file(query)
        media_path = await asyncio.to_thread(self._require_media_file, media)
        executable = await asyncio.to_thread(self._resolve_executable)
        extra_args = _parse_extra_args(self._config.args)

        try:
            await asyncio.to_thread(_launch_potplayer, executable, media_path, extra_args)
        except OSError as exc:
            raise SourceError(
                FailureReason.NO_USABLE_METADATA,
                detail=f"无法启动 PotPlayer: {exc.strerror or exc}",
            ) from exc


class Plugin(PlaybackPlugin):
    config_model = PotPlayerConfig

    @classmethod
    @override
    def descriptor(cls) -> SourceDescriptor:
        return SourceDescriptor(
            id=PLUGIN_ID,
            name="PotPlayer (本机)",
            version="0.2.0",
            capabilities=frozenset({SourceCapability.PLAYBACK.value}),
            urls=(),
        )

    @override
    def build_playback(self, context: PluginContext, config: BaseModel) -> PlaybackProvider:
        if not isinstance(config, PotPlayerConfig):
            raise TypeError("unexpected config type")
        return PotPlayerProvider(config)


# 供手动探测安装路径时使用; 插件加载不依赖此入口.
if __name__ == "__main__":
    configured = os.environ.get("POTPLAYER_PATH", "")
    print(_find_executable(configured) or "not found")
