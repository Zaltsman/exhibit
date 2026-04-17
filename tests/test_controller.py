import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os

# ---------------------------------------------------------------------------
# Path setup
# The tests folder is separate from the controller folder.
# This line tells Python where to find controller.py and config.py
# so we can import them without moving files around.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'controller'))

import controller
from config import KEY_MAP, PAUSE_KEY


# ---------------------------------------------------------------------------
# What are these tests doing overall?
#
# We are testing the LOGIC of the controller in isolation — meaning we don't
# need a real phone, a real video file, or a real mpv process to run these.
# Instead we use "mocks" which are fake stand-ins that pretend to be the real
# thing and let us check whether our code called them correctly.
#
# Think of it like a fire drill — you test the evacuation procedure without
# actually setting the building on fire.
# ---------------------------------------------------------------------------


class TestHandleKeypress(unittest.TestCase):
    """
    Tests for handle_keypress() — the main entry point that receives
    keypresses from the phone and routes them to the correct action.
    """

    def setUp(self):
        """
        Reset controller state before every single test in this class.
        This ensures tests don't affect each other — each one starts clean.
        """
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    @patch('controller.play_video')
    def test_all_video_keys_trigger_play(self, mock_play):
        """
        Pressing any of keys 1-9 should call play_video() with that key.
        We loop through every key in KEY_MAP to confirm all of them work,
        not just the first one.
        """
        for key in KEY_MAP.keys():
            controller.handle_keypress(key)
            # Confirm play_video was called with exactly this key
            mock_play.assert_called_with(key)

    @patch('controller.toggle_pause')
    def test_pause_key_triggers_toggle_pause(self, mock_pause):
        """
        Pressing the pause key (defined in config.py as '0') should
        call toggle_pause() exactly once — not zero times, not twice.
        """
        controller.handle_keypress(PAUSE_KEY)
        mock_pause.assert_called_once()

    @patch('controller.play_video')
    @patch('controller.toggle_pause')
    def test_unmapped_keys_do_nothing(self, mock_pause, mock_play):
        """
        Pressing keys that aren't in KEY_MAP and aren't the pause key
        should be silently ignored. No video should play, no pause should
        toggle. This prevents the system from crashing if someone presses
        an unexpected key like * or #.
        """
        controller.handle_keypress('*')
        controller.handle_keypress('#')
        controller.handle_keypress('A')  # extra edge case

        mock_play.assert_not_called()
        mock_pause.assert_not_called()


class TestStopVideo(unittest.TestCase):
    """
    Tests for stop_video() — confirms it correctly terminates the mpv
    process and decides whether to show the idle screen based on context.
    """

    def setUp(self):
        """Reset state before each test"""
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    @patch('controller.show_idle_screen')
    def test_stop_does_nothing_when_nothing_is_playing(self, mock_idle):
        """
        If stop_video() is called when no video is playing, it should
        exit quietly without crashing and without showing the idle screen.
        current_video is None here, which simulates nothing playing.
        """
        controller.stop_video()
        mock_idle.assert_not_called()

    @patch('controller.show_idle_screen')
    def test_stop_terminates_mpv_process(self, mock_idle):
        """
        When a video is playing, stop_video() should call terminate()
        on the mpv process. We use a MagicMock to simulate the mpv process
        without needing a real video file or real mpv installed.
        """
        mock_process = MagicMock()
        controller.current_video = mock_process

        controller.stop_video(return_to_idle=False)

        # Confirm terminate() was called on the fake mpv process
        mock_process.terminate.assert_called_once()

    @patch('controller.show_idle_screen')
    def test_stop_shows_idle_screen_on_hangup(self, mock_idle):
        """
        When return_to_idle=True (the hang-up flow), stop_video()
        should show the idle screen after terminating the video.
        This is what happens when the participant hangs up the phone.
        """
        mock_process = MagicMock()
        controller.current_video = mock_process

        controller.stop_video(return_to_idle=True)

        mock_process.terminate.assert_called_once()
        mock_idle.assert_called_once()

    @patch('controller.show_idle_screen')
    def test_stop_skips_idle_screen_when_switching_videos(self, mock_idle):
        """
        When return_to_idle=False (switching between videos), stop_video()
        should NOT show the idle screen. This prevents a visible flash of
        the idle screen when a participant presses a new number key while
        a video is already playing.
        """
        mock_process = MagicMock()
        controller.current_video = mock_process

        controller.stop_video(return_to_idle=False)

        mock_process.terminate.assert_called_once()
        mock_idle.assert_not_called()

    @patch('controller.show_idle_screen')
    def test_stop_resets_state_correctly(self, mock_idle):
        """
        After stopping, current_video should be None and is_paused
        should be False regardless of what state they were in before.
        This ensures the system is always in a clean state after a stop.
        """
        mock_process = MagicMock()
        controller.current_video = mock_process
        controller.is_paused = True  # simulate a paused video being stopped

        controller.stop_video(return_to_idle=False)

        self.assertIsNone(controller.current_video)
        self.assertFalse(controller.is_paused)


class TestHandleHangup(unittest.TestCase):
    """
    Tests for handle_hangup() — called by the SIP layer when the
    participant physically hangs up the phone receiver.
    """

    def setUp(self):
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    @patch('controller.stop_video')
    def test_hangup_stops_video_and_returns_to_idle(self, mock_stop):
        """
        Hanging up should always call stop_video() with return_to_idle=True.
        This is the most important behavior in the whole system — hanging up
        the phone must always return the exhibit to its idle state.
        """
        controller.handle_hangup()
        mock_stop.assert_called_once_with(return_to_idle=True)


class TestTogglePause(unittest.TestCase):
    """
    Tests for toggle_pause() — confirms pause state is tracked correctly
    and that the mpv IPC socket is written to properly.
    """

    def setUp(self):
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    def test_pause_does_nothing_when_no_video_playing(self):
        """
        Pressing pause when nothing is playing should not crash the system.
        current_video is None here, which is the no-video state.
        """
        try:
            controller.toggle_pause()
        except Exception as e:
            self.fail(
                f"toggle_pause() raised an unexpected exception "
                f"when no video was playing: {e}"
            )

    def test_pause_toggles_is_paused_from_false_to_true(self):
        """
        When a video is playing and is_paused is False,
        calling toggle_pause() should set is_paused to True.
        We mock the socket file so we don't need a real mpv process.
        """
        controller.current_video = MagicMock()
        controller.is_paused = False

        # mock_open simulates writing to the mpv socket file
        # without needing a real socket or real mpv running
        with patch('builtins.open', mock_open()):
            controller.toggle_pause()

        self.assertTrue(controller.is_paused)

    def test_pause_toggles_is_paused_from_true_to_false(self):
        """
        When a video is playing and is_paused is True (already paused),
        calling toggle_pause() should set is_paused back to False.
        Tested separately from the above to be explicit about both directions.
        """
        controller.current_video = MagicMock()
        controller.is_paused = True

        with patch('builtins.open', mock_open()):
            controller.toggle_pause()

        self.assertFalse(controller.is_paused)


class TestVideoSwitching(unittest.TestCase):
    """
    Tests for the video switching scenario — what happens when a participant
    presses a new number key while a video is already playing.
    This is an important real-world case that needs explicit testing.
    """

    def setUp(self):
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    @patch('controller.stop_video')
    @patch('os.path.exists', return_value=True)
    @patch('subprocess.Popen')
    @patch('threading.Thread')
    def test_playing_new_video_stops_current_first(
        self, mock_thread, mock_popen, mock_exists, mock_stop
    ):
        """
        If a video is already playing and the participant presses a new
        number key, the current video must be stopped before the new one
        starts. This confirms stop_video() is called with return_to_idle=False
        so the idle screen doesn't flash between videos.
        """
        # Simulate a video already playing
        controller.current_video = MagicMock()

        controller.play_video('2')

        # stop_video should have been called with return_to_idle=False
        mock_stop.assert_called_once_with(return_to_idle=False)

class TestKeypressWhileVideoPlaying(unittest.TestCase):
    """
    Tests for the old-school phone behavior — once a video is playing,
    pressing another number key should be ignored. The participant
    must hang up first to choose a different video.
    """

    def setUp(self):
        controller.current_video = None
        controller.is_paused = False
        controller.chromium_process = None

    @patch('controller.play_video')
    def test_keypress_ignored_when_video_playing(self, mock_play):
        """
        If a video is currently playing and the participant presses
        a number key, play_video() should NOT be called.
        They must hang up first.
        """
        # Simulate a video already playing
        controller.current_video = MagicMock()

        controller.handle_keypress('2')

        mock_play.assert_not_called()

    @patch('controller.toggle_pause')
    def test_pause_still_works_while_video_playing(self, mock_pause):
        """
        The pause key (0) should always work even while a video
        is playing — it's a playback control, not a video selector.
        """
        controller.current_video = MagicMock()

        controller.handle_keypress('0')

        mock_pause.assert_called_once()

    @patch('controller.play_video')
    def test_keypress_works_when_no_video_playing(self, mock_play):
        """
        Confirm that keypresses work normally when no video is playing.
        This ensures the ignore logic only fires when a video is active.
        """
        controller.current_video = None

        controller.handle_keypress('3')

        mock_play.assert_called_once_with('3')

if __name__ == '__main__':
    # This allows running the tests directly with:
    # python3 tests/test_controller.py
    # as well as via pytest
    unittest.main()