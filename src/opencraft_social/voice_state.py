from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import PolicyError


class ListeningMode(str, Enum):
    OFF = "off"
    SPATIAL = "spatial"
    LOBBY = "lobby"
    HYBRID = "hybrid"


class CaptureMode(str, Enum):
    OFF = "off"
    PUSH_TO_TALK = "push-to-talk"
    VOICE_ACTIVITY = "voice-activity"
    OPEN_MIC = "open-mic"


@dataclass(slots=True)
class VoiceState:
    listening: ListeningMode = ListeningMode.OFF
    capture: CaptureMode = CaptureMode.OFF
    microphone_permission: bool = False
    transmitting: bool = False
    agent_connected: bool = False
    agent_listening: bool = False
    recording: bool = False

    def set_listening(self, mode: ListeningMode) -> None:
        """Changing how others are heard never enables microphone capture."""
        self.listening = mode

    def grant_microphone_permission(self) -> None:
        self.microphone_permission = True

    def set_capture(self, mode: CaptureMode) -> None:
        if mode is not CaptureMode.OFF and not self.microphone_permission:
            raise PolicyError("microphone permission is required before capture can be enabled")
        self.capture = mode
        if mode is CaptureMode.OFF:
            self.transmitting = False
            self.agent_listening = False

    def begin_transmission(self, *, push_to_talk_pressed: bool = False) -> None:
        if self.capture is CaptureMode.OFF:
            raise PolicyError("capture is disabled")
        if self.capture is CaptureMode.PUSH_TO_TALK and not push_to_talk_pressed:
            raise PolicyError("push-to-talk must be held")
        self.transmitting = True

    def stop_transmission(self) -> None:
        self.transmitting = False

    def connect_agent(self) -> None:
        self.agent_connected = True

    def disconnect_agent(self) -> None:
        self.agent_connected = False
        self.agent_listening = False

    def enable_agent_listening(self, *, owner_consent: bool) -> None:
        if not self.agent_connected:
            raise PolicyError("agent is not connected")
        if not owner_consent:
            raise PolicyError("explicit owner consent is required")
        if not self.microphone_permission or self.capture is CaptureMode.OFF:
            raise PolicyError("microphone capture must be explicitly enabled")
        self.agent_listening = True

    def disable_agent_listening(self) -> None:
        self.agent_listening = False

    def set_recording(self, enabled: bool, *, all_required_consents: bool = False) -> None:
        if enabled and not all_required_consents:
            raise PolicyError("recording requires explicit participant consent")
        self.recording = enabled

    def reset_after_disconnect(self) -> None:
        """Sensitive states never resume automatically after reconnecting."""
        self.capture = CaptureMode.OFF
        self.transmitting = False
        self.agent_listening = False
        self.recording = False
