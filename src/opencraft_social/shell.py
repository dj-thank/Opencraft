from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import PolicyError


class ShellMode(str, Enum):
    LOBBY = "lobby"
    WORLD = "world"


class Overlay(str, Enum):
    NONE = "none"
    PAUSE = "pause"
    BUILD = "build"
    AGENT = "agent"
    SOCIAL = "social"
    VOICE = "voice"
    MAP = "map"
    AVATAR = "avatar"
    SETTINGS = "settings"
    INVITE = "invite"
    CHAT = "chat"


@dataclass(slots=True)
class WorldFirstShell:
    mode: ShellMode = ShellMode.LOBBY
    overlay: Overlay = Overlay.NONE

    def enter_world(self) -> None:
        self.mode = ShellMode.WORLD
        self.overlay = Overlay.NONE

    def return_to_lobby(self) -> None:
        self.mode = ShellMode.LOBBY
        self.overlay = Overlay.NONE

    def open_overlay(self, overlay: Overlay) -> None:
        if overlay is Overlay.NONE:
            self.overlay = Overlay.NONE
            return
        if self.mode is ShellMode.LOBBY and overlay not in {
            Overlay.AVATAR,
            Overlay.SETTINGS,
            Overlay.INVITE,
        }:
            raise PolicyError(f"{overlay.value} is available only over the world")
        self.overlay = overlay

    def close_overlay(self) -> None:
        self.overlay = Overlay.NONE

    @property
    def primary_screen(self) -> str:
        return self.mode.value
