import subprocess
import os
import sys
import time
import threading
import socket

from config import KEY_MAP, EXHIBIT_DIR

# ---------------------------------------------------------------------------
# State tracking
# current_video — the running mpv process, or None if nothing is playing
# idle_process — holds the idle screen mpv process
# call_start_time — when the current call started, used to ignore early hangups
# ---------------------------------------------------------------------------
current_video = None
idle_process = None
call_start_time = None


def play_video(key):
    """
    Kill idle screen, stop any current video, then launch the video
    mapped to the pressed key in fullscreen using mpv.
    Audio is routed to the ALSA loopback (hw:2,0) so baresip
    can stream it to the phone handset via RTP.
    """
    global current_video, call_start_time

    # Kill idle screen so mpv can take fullscreen
    subprocess.run(['pkill', '-f', 'idle.mp4'], capture_output=True)
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
        '--audio-device=alsa/hw:2,0',
        video_path
    ]

    env = os.environ.copy()
    env['DISPLAY'] = ':0'
    env['XAUTHORITY'] = '/home/pi/.Xauthority'
    current_video = subprocess.Popen(args, env=env)
    call_start_time = time.time()

    # When video ends naturally, return to idle screen
    video_process = current_video
    def wait_for_video_end():
        video_process.wait()
        print("Video ended naturally — returning to idle")
        show_idle_screen()

    threading.Thread(target=wait_for_video_end, daemon=True).start()


def stop_video(return_to_idle=True):
    """
    Stop the currently playing video.
    return_to_idle=False when switching between videos to avoid
    flashing the idle screen between plays.
    """
    global current_video

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

    if return_to_idle:
        print("Returning to idle screen")
        show_idle_screen()


def show_idle_screen():
    global idle_process

    # Clear all baresip calls when returning to idle
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b'/hangupall\n', ('127.0.0.1', 5555))
        s.close()
        time.sleep(0.3)
    except Exception:
        pass

    if idle_process is not None and idle_process.poll() is None:
        print("Idle screen already showing")
        return

    print("Launching idle screen")

    env = os.environ.copy()
    env['DISPLAY'] = ':0'
    env['XAUTHORITY'] = '/home/pi/.Xauthority'

    idle_process = subprocess.Popen([
        'mpv',
        '--fs',
        '--loop=inf',
        '--no-audio',
        '--really-quiet',
        '/home/pi/exhibit/web/idle.mp4'
    ], env=env)


def handle_keypress(key):
    """
    Route a keypress to the correct action.
    Keys 1-7 play videos. Key 0 stops the current video.
    If a video is already playing, number keys are ignored —
    participant must hang up first to choose a different video.
    """
    print(f"Keypress received: {key}")

    if key == '0':
        stop_video(return_to_idle=True)
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