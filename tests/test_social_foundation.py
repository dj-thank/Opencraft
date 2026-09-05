from __future__ import annotations

import unittest

from opencraft_social.model import PolicyError
from opencraft_social.session import ArrivalSession
from opencraft_social.shell import Overlay, ShellMode, WorldFirstShell
from opencraft_social.voice_state import CaptureMode, ListeningMode, VoiceState


class WorldFirstShellTests(unittest.TestCase):
    def test_only_lobby_and_world_are_primary_modes(self):
        self.assertEqual({mode.value for mode in ShellMode}, {"lobby", "world"})

    def test_world_tools_are_overlays_not_primary_screens(self):
        shell = WorldFirstShell()
        shell.enter_world()
        shell.open_overlay(Overlay.AGENT)
        self.assertEqual(shell.primary_screen, "world")
        self.assertEqual(shell.overlay, Overlay.AGENT)
        shell.close_overlay()
        self.assertEqual(shell.primary_screen, "world")

    def test_build_overlay_cannot_open_from_lobby(self):
        with self.assertRaises(PolicyError):
            WorldFirstShell().open_overlay(Overlay.BUILD)


class VoicePolicyTests(unittest.TestCase):
    def test_listening_mode_never_enables_capture(self):
        state = VoiceState()
        state.set_listening(ListeningMode.SPATIAL)
        self.assertEqual(state.capture, CaptureMode.OFF)
        self.assertFalse(state.transmitting)

    def test_microphone_permission_precedes_capture(self):
        state = VoiceState()
        with self.assertRaises(PolicyError):
            state.set_capture(CaptureMode.PUSH_TO_TALK)
        state.grant_microphone_permission()
        state.set_capture(CaptureMode.PUSH_TO_TALK)
        with self.assertRaises(PolicyError):
            state.begin_transmission(push_to_talk_pressed=False)
        state.begin_transmission(push_to_talk_pressed=True)
        self.assertTrue(state.transmitting)

    def test_connecting_agent_does_not_enable_listening(self):
        state = VoiceState()
        state.connect_agent()
        self.assertTrue(state.agent_connected)
        self.assertFalse(state.agent_listening)

    def test_agent_listening_requires_owner_consent_and_capture(self):
        state = VoiceState()
        state.connect_agent()
        with self.assertRaises(PolicyError):
            state.enable_agent_listening(owner_consent=True)
        state.grant_microphone_permission()
        state.set_capture(CaptureMode.PUSH_TO_TALK)
        with self.assertRaises(PolicyError):
            state.enable_agent_listening(owner_consent=False)
        state.enable_agent_listening(owner_consent=True)
        self.assertTrue(state.agent_listening)

    def test_sensitive_states_reset_after_disconnect(self):
        state = VoiceState()
        state.grant_microphone_permission()
        state.set_capture(CaptureMode.OPEN_MIC)
        state.begin_transmission()
        state.connect_agent()
        state.enable_agent_listening(owner_consent=True)
        state.set_recording(True, all_required_consents=True)
        state.reset_after_disconnect()
        self.assertEqual(state.capture, CaptureMode.OFF)
        self.assertFalse(state.transmitting)
        self.assertFalse(state.agent_listening)
        self.assertFalse(state.recording)

    def test_arrival_always_enters_with_sensitive_states_off(self):
        session = ArrivalSession.create()
        session.voice.grant_microphone_permission()
        session.voice.set_capture(CaptureMode.OPEN_MIC)
        session.enter()
        self.assertTrue(session.is_in_world)
        self.assertEqual(session.voice.capture, CaptureMode.OFF)


if __name__ == "__main__":
    unittest.main()
