from __future__ import annotations

from dataclasses import dataclass

from .shell import ShellMode, WorldFirstShell
from .voice_state import VoiceState


@dataclass(slots=True)
class ArrivalSession:
    """Join state whose sensitive permissions always begin disabled."""

    shell: WorldFirstShell
    voice: VoiceState
    temporary_avatar: bool = True

    @classmethod
    def create(cls) -> "ArrivalSession":
        return cls(shell=WorldFirstShell(), voice=VoiceState())

    def enter(self) -> None:
        self.voice.reset_after_disconnect()
        self.shell.enter_world()

    def leave(self) -> None:
        self.voice.reset_after_disconnect()
        self.shell.return_to_lobby()

    @property
    def is_in_world(self) -> bool:
        return self.shell.mode is ShellMode.WORLD
