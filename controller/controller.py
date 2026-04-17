import subprocess
import os
import sys
import time
call_start_time = None

# config.py lives in the same folder and holds all settings
# like which key maps to which video, paths, etc.
from config import KEY_MAP, PAUSE_KEY, EXHIBIT_DIR, IDLE_PAGE, MPV_FULLSCREEN

# ---------------------------------------------------------------------------
# State tracking
# We keep track of the mpv process so we can pause, resume, or stop it.
# current_video holds the running mpv process, or None if nothing is playing.
# is_paused tracks whether we have paused the video so we can toggle correctly.
# chromium_process holds the Chromium window so we don't open duplicate windows.
# ---------------------------------------------------------------------------
current_video = None
is_paused = False
chromium_process = None


def play_video(key):
    """
    Stop any currently playing video, then launch the video
    mapped to the pressed key in fullscreen using mpv.
    """
    global current_video, is_paused, call_start_time

    import time
    import threading

    # Kill any existing Chromium window so mpv can go fullscreen
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
    print(f"mpv launched with PID: {current_video.pid}")
    time.sleep(0.5)
    print(f"mpv still running: {current_video.poll() is None}")
    is_paused = False
    call_start_time = time.time()
    print(f"Call start time recorded: {call_start_time}")

    def wait_for_video_end():
        current_video.wait()
        print("Video ended naturally — returning to idle")
        show_idle_screen()

    threading.Thread(target=wait_for_video_end, daemon=True).start()


def stop_video(return_to_idle=True):
    """
    Stop the currently playing video.
    return_to_idle controls whether we show the idle screen after stopping.
    We pass False when switching directly between videos so we don't
    flash the idle screen between plays.
    """
    global current_video, is_paused

    if current_video is None:
        # Nothing is playing — nothing to stop
        return

    print("Stopping current video")
    current_video.terminate()

    try:
        # Give mpv 3 seconds to shut down cleanly
        current_video.wait(timeout=3)
    except subprocess.TimeoutExpired:
        # If it doesn't respond, force kill it
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
    mpv has its own pause command which is more reliable than
    sending OS-level signals.
    """
    global is_paused

    if current_video is None:
        # No video is playing — nothing to pause
        print("No video playing — ignoring pause key")
        return

    # Send the pause toggle command directly to mpv via its socket
    # This is the correct way to pause mpv rather than using SIGSTOP
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
    We track the Chromium process so we only ever have one window open.
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
    If a video is already playing, keypresses are ignored —
    the participant must hang up first to choose a different video.
    This simulates old-school phone behavior and prevents accidental
    mid-video interruptions.
    """
    print(f"Keypress received: {key}")

    if key == PAUSE_KEY:
        # Pause key always works regardless of state
        toggle_pause()
        return

    if current_video is not None:
        # A video is already playing — ignore video selection keys
        print(f"Key {key} ignored — video already playing, hang up to choose another")
        return

    if key in KEY_MAP:
        play_video(key)
    else:
        print(f"Key {key} is not mapped — ignoring")


def handle_hangup():
    global call_start_time
    
    # Ignore hangup if it comes within 2 seconds of call starting
    # This prevents the phone's automatic BYE from stopping the video
    if call_start_time is not None:
        elapsed = time.time() - call_start_time
        print(f"Hangup elapsed time: {elapsed:.2f}s")
        if elapsed < 2.0:
            print(f"Ignoring early hangup ({elapsed:.1f}s after call start)")
            return
    
    print("Phone hung up — stopping video and returning to idle")
    stop_video(return_to_idle=True)