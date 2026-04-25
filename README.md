# Exhibit — Interactive VoIP Phone Art Installation

An interactive art installation where participants pick up a vintage VoIP phone, dial a number (1–9), and a corresponding video plays fullscreen on a monitor with audio through the phone handset.

---

## How It Works

1. Participant picks up the phone handset
2. Dials a number (1–9) to select a video
3. Video plays fullscreen on the monitor
4. Audio streams through the phone handset via SIP/RTP
5. Participant hangs up to return to the idle screen
6. Pressing `0` during a video stops it early

---

## Hardware

| Component | Details |
|-----------|---------|
| Raspberry Pi 5 8GB | Runs everything |
| Cisco CP-8811-3PCC MPP phone | VoIP phone — keypad + handset audio |
| Network switch (8-port unmanaged) | Creates private LAN between Pi and phone |
| Monitor with HDMI input | Displays videos and idle screen |
| Micro-HDMI to HDMI cable | Pi → monitor (use MICRO not mini) |
| 2x Ethernet cables | Pi → switch, phone → switch |

### Network
| Device | Interface | IP |
|--------|-----------|-----|
| Raspberry Pi | eth0 (switch) | 192.168.10.1 |
| Raspberry Pi | wlan0 (WiFi) | assigned by venue |
| Cisco phone | — | 192.168.10.2 |

The switch creates a private LAN between the Pi and phone. The Pi's WiFi is used for SSH access only. No internet is required for the exhibit to function.

---

## Software Stack

| Component | Purpose |
|-----------|---------|
| **Kamailio 6.0.1** | SIP proxy — registers phone, routes calls to baresip |
| **baresip 1.1.0** | SIP media endpoint — answers calls, streams audio via RTP |
| **ALSA loopback** | Virtual audio bridge between mpv and baresip |
| **mpv** | Plays videos fullscreen, outputs audio to loopback |
| **sip_monitor.py** | Watches SIP traffic via tcpdump, triggers video playback |
| **controller.py** | Maps keypresses to videos, manages mpv and idle screen |

### Audio Architecture
```
mpv plays video
→ audio output to ALSA loopback hw:2,0
→ baresip reads from loopback hw:2,1
→ baresip sends RTP/PCMU audio over Ethernet
→ Cisco phone plays through handset
```

> **Note:** The ALSA loopback card number (currently hw:2) can change if USB devices
> are connected or disconnected. Always verify with `aplay -l` after reboot.

---

## Repository Structure

```
exhibit/
├── controller/
│   ├── config.py          # Key→video mapping and paths
│   ├── controller.py      # Video playback and idle screen logic
│   └── sip_monitor.py     # SIP traffic watcher (tcpdump-based)
├── kamailio/
│   └── kamailio.cfg       # Kamailio SIP server configuration
├── tests/
│   └── test_controller.py # Unit tests
├── videos/                # Video files (not in git — transfer separately)
│   ├── video1.mp4
│   ├── video2.mp4
│   └── ...
├── web/
│   ├── idle.mp4           # Idle screen looping video (not in git)
│   └── images/
│       └── idle.gif       # Placeholder (replaced by idle.mp4)
├── setup.sh               # On-site setup script (run once on fresh Pi)
└── README.md
```

> **Video requirements:** All videos must be 1080p (1920×1080), 24fps, H.264/AAC.
> 4K or high-framerate videos will cause A/V desync on the Pi 5.
> To convert: `ffmpeg -i input.mp4 -vf scale=1920:1080 -r 24 -c:v libx264 -crf 23 -c:a aac -b:a 192k output.mp4`

---

## Files NOT in Git

These files exist on the Pi but are excluded from the repo:

| Path | Reason |
|------|---------|
| `videos/` | Too large for GitHub (400–500MB each) |
| `web/idle.mp4` | Large file, transfer separately |
| `/home/pi/.baresip/config` | baresip config — created by setup.sh |
| `/home/pi/.baresip/accounts` | baresip accounts — created by setup.sh |

Transfer videos and idle.mp4 to a new device via USB drive or `scp`.

---

## Daily Startup

Run every morning after powering on the Pi and phone:

```bash
export DISPLAY=:0
xhost +local:root
pkill baresip; pkill chromium; pkill mpv
rm -f /home/pi/.config/chromium/Singleton*
sudo modprobe snd-aloop
baresip -f /home/pi/.baresip &
DISPLAY=:0 python3 /home/pi/exhibit/controller/sip_monitor.py
```

**Step by step:**
1. Plug in Pi power (USB-C)
2. Plug in phone power
3. Wait 30 seconds for Pi to boot
4. SSH in from laptop: `ssh pi@<PI_WIFI_IP>`
5. Run the startup command above
6. Pick up phone, press 1, confirm video plays with audio
7. Put laptop away — exhibit is running

## Evening Shutdown

```bash
sudo shutdown now
```

---

## Contingency Plan

| Problem | Fix |
|---------|-----|
| No audio / system unresponsive | Ctrl+C, run startup command again |
| Phone shows "network connection failure" | Unplug phone power, wait 10s, replug |
| Video freezes or idle screen stuck | `pkill chromium && pkill mpv`, hang up and retry |
| Pi unreachable over SSH | Use keyboard/mouse directly on Pi desktop |
| Everything broken | `sudo reboot`, wait 45s, run startup command |

---

## On-Site Setup (New Device)

Target: 30–35 minutes per device.

### Phase 1 — First boot (5 min)
Complete the Raspberry Pi setup wizard. Set username to `pi`.

### Phase 2 — Enable SSH (2 min)
```bash
sudo raspi-config
# Interface Options → SSH → Enable
hostname -I  # note the WiFi IP
```

### Phase 3 — Run setup script (15–20 min)
```bash
ssh pi@<IP>
curl -sSL https://raw.githubusercontent.com/zaltsman/exhibit/main/setup.sh | bash
```

### Phase 4 — Configure Cisco phone web UI (5 min)
Open `http://192.168.10.2/admin` in Chromium on the Pi. Log in, click **advanced**.

**Voice → System (Static IP):**
- IP: `192.168.10.2`, Mask: `255.255.255.0`, Gateway: `192.168.10.1`, DNS: `8.8.8.8`

**Voice → Ext 1:**
- Proxy + Outbound Proxy: `192.168.10.1`
- User ID: `phone`, Display Name: `phone`
- DTMF Tx Method: `INFO`
- Dial Plan: `([1-9]|*xx|[3469]11|0|00|[2-9]xxxxxx|1xxx[2-9]xxxxxxS0|xxxxxxxxxxx.)`

**Voice → Regional (set to `!` for silence):**
- Dial Tone, Busy Tone, Reorder Tone, Off Hook Warning Tone

### Phase 5 — Transfer videos (time varies)
Copy `videos/` folder and `web/idle.mp4` via USB drive or `scp`.

### Phase 6 — Test (5 min)
Run startup command, pick up phone, press 1, confirm video and audio work.

---

## baresip Configuration

These files are created by `setup.sh` but documented here for reference.

**`/home/pi/.baresip/config`**
```
module_path         /usr/lib/baresip/modules
module              g711.so
module              alsa.so
module              account.so
module              contact.so
module              cons.so
module              aubridge.so
module              menu.so
net_interface       eth0
sip_listen          192.168.10.1:5061
sip_trans_def       UDP
audio_player        alsa,hw:2,1
audio_source        alsa,hw:2,1
audio_alert         alsa,hw:2,1
audio_codecs        pcmu/8000/1
rtp_timeout         3600
```

**`/home/pi/.baresip/accounts`**
```
<sip:exhibit@192.168.10.1:5061;transport=udp>;regint=0;inreq_allowed=yes;catchall=yes;answermode=auto;audio_codecs=pcmu/8000/1
```

> **Critical:** `net_interface eth0` is required. Without it baresip binds to wlan0
> and never receives SIP traffic from the phone.
> `menu.so` is required for `answermode=auto` to work.

---

## Running Tests

```bash
cd /home/pi/exhibit
python3 -m pytest tests/test_controller.py -v
```

---

## Key Commands Reference

```bash
# SSH into Pi
ssh pi@<WIFI_IP>

# Check phone registration
sudo kamctl ul show

# Check Kamailio status
sudo systemctl status kamailio

# Check baresip running
ps aux | grep baresip | grep -v grep

# Check ALSA loopback card number
aplay -l

# Kamailio — copy config and restart
sudo cp /home/pi/exhibit/kamailio/kamailio.cfg /etc/kamailio/kamailio.cfg
sudo kamailio -c /etc/kamailio/kamailio.cfg
sudo systemctl restart kamailio

# Convert video to correct format (run on laptop or Pi)
ffmpeg -i input.mp4 -vf scale=1920:1080 -r 24 -c:v libx264 -crf 23 -c:a aac -b:a 192k output.mp4
```
