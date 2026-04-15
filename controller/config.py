# Key to video file mapping
KEY_MAP = {
    '1': 'videos/video1.mp4',
    '2': 'videos/video2.mp4',
    '3': 'videos/video3.mp4',
    '4': 'videos/video4.mp4',
    '5': 'videos/video5.mp4',
    '6': 'videos/video6.mp4',
    '7': 'videos/video7.mp4',
    '8': 'videos/video8.mp4',
    '9': 'videos/video9.mp4',
}

# Control keys
PAUSE_KEY = '0'

# Hang up = stop video and return to idle
# This is handled as a call-ended event, not a keypress

# Paths
EXHIBIT_DIR = '/home/pi/exhibit'
WEB_DIR = '/home/pi/exhibit/web'
IDLE_PAGE = '/home/pi/exhibit/web/index.html'

# Kamailio connection
KAMAILIO_HOST = '127.0.0.1'
KAMAILIO_PORT = 5060
KAMAILIO_EVAPI_PORT = 8448

# Video player settings
MPV_FULLSCREEN = True