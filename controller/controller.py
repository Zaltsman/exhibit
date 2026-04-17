import subprocess
import os
import sys
import time
import threading

from config import KEY_MAP, PAUSE_KEY, EXHIBIT_DIR, IDLE_PAGE, MPV_FULLSCREEN

# ---------------------------------------------------------------------------
# State tracking
# current_video — the running mpv process, or None if nothing is playing
# is_paused — whether the current video is paused
# chromium_process — the Chromium kiosk window
# call_start_time — when the current call started, used to ignore early hangups
# ---------------------------------------------------------------------------
current_video = None
is_paused = False
chromium_process = None
call_start_time = None


def play_video(key):
    """
    Kill Chromium, stop any current video, then launch the video
    mapped to the pressed key in fullscreen using mpv.
    Audio is routed to the ALSA loopback (hw:3,0) so baresip
    can stream it to the phone handset via RTP.
    """
    global current_video, is_paused, call_start_time

    # Kill Chromium so mpv can take fullscreen
    subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
    time.sleep(0.5)

    # Stop whatever is currently playing first
    stop_video(return_to_idle=False)

    # Build the full path to the video file
    video_path = os.path.join(EXHIBIT_DIR, KEY_MAP[key])

    # Safety check — warn if the file doesn't exist rather than crashing
    if not os.path.exists(video_path):
        print(f"Warning: video file not found at {video_path}")
        print("Check that the file exists and the name matches config.py")
        return

    print(f"Playing video for key {key}: {video_path}")

    # Launch mpv fullscreen with audio routed to ALSA loopback
    # --ao=alsa and --audio-device route audio to hw:3,0
    # baresip reads from hw:3,1 (the other end of the loopback)
    # and streams it to the phone as RTP
    args = [
        'mpv',
        '--fs',
        '--input-ipc-server=/tmp/mpv-socket',
        '--ao=alsa',
        '--audio-device=alsa/hw:3,0',
        video_path
    ]

    env = os.environ.copy()
    env['DISPLAY'] = ':0'
    env['XAUTHORITY'] = '/home/pi/.Xauthority'
    current_video = subprocess.Popen(args, env=env)
    is_paused = False
    call_start_time = time.time()

    # When video ends naturally, return to idle screen
    # Runs in background thread so it doesn't block the main loop
    def wait_for_video_end():
        current_video.wait()
        print("Video ended naturally — returning to idle")
        show_idle_screen()

    threading.Thread(target=wait_for_video_end, daemon=True).start()


def stop_video(return_to_idle=True):
    """
    Stop the currently playing video.
    return_to_idle=False when switching between videos to avoid
    flashing the idle screen between plays.
    """
    global current_video, is_paused

    if current_video is None:
        return

    print("Stopping current video")
    current_video.terminate()

    try:
        current_video.wait(timeout=3)
    except subprocess.TimeoutExpired:
        print("mpv did not stop cleanly — force killing")
        current_video.kill()

    current_video = None
    is_paused = False

    if return_to_idle:
        print("Returning to idle screen")
        show_idle_screen()


def toggle_pause():
    """
    Pause or resume the current video using mpv's IPC socket.
    """
    global is_paused

    if current_video is None:
        print("No video playing — ignoring pause key")
        return

    pause_cmd = '{ "command": ["cycle", "pause"] }\n'
    try:
        with open('/tmp/mpv-socket', 'w') as sock:
            sock.write(pause_cmd)
        is_paused = not is_paused
        print(f"Video {'paused' if is_paused else 'resumed'}")
    except Exception as e:
        print(f"Could not send pause command to mpv: {e}")


def show_idle_screen():
    """
    Show the idle screen in Chromium kiosk mode.
    Tracks the process to avoid opening duplicate windows.
    """
    global chromium_process

    if chromium_process is not None and chromium_process.poll() is None:
        print("Idle screen already showing")
        return

    print("Launching idle screen in Chromium kiosk mode")

    env = os.environ.copy()
    env['DISPLAY'] = ':0'
    env['XAUTHORITY'] = '/home/pi/.Xauthority'

    chromium_process = subprocess.Popen([
        'chromium',
        '--kiosk',
        '--noerrdialogs',
        '--disable-infobars',
        '--disable-session-crashed-bubble',
        '--no-sandbox',
        f'file://{IDLE_PAGE}'
    ], env=env)


def handle_keypress(key):
    """
    Route a keypress to the correct action.
    Keys 1-7 play videos. Key 0 pauses/resumes.
    If a video is already playing, number keys are ignored —
    participant must hang up first to choose a different video.
    """
    print(f"Keypress received: {key}")

    if key == PAUSE_KEY:
        toggle_pause()
        return

    if current_video is not None:
        print(f"Key {key} ignored — video already playing, hang up to choose another")
        return

    if key in KEY_MAP:
        play_video(key)
    else:
        print(f"Key {key} is not mapped — ignoring")


def handle_hangup():
    """
    Called when the participant hangs up the phone.
    Ignores hangups within 2 seconds of call start —
    the phone sends an automatic BYE shortly after connecting
    which would otherwise stop the video prematurely.
    """
    global call_start_time

    if call_start_time is not None:
        elapsed = time.time() - call_start_time
        if elapsed < 2.0:
            print(f"Ignoring early hangup ({elapsed:.1f}s after call start)")
            return

    print("Phone hung up — stopping video and returning to idle")
    stop_video(return_to_idle=True)