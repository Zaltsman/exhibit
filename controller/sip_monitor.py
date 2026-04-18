import subprocess
import sys
import os
import datetime

# ---------------------------------------------------------------------------
# sip_monitor.py
#
# Watches SIP network traffic directly using tcpdump.
# Looks for INVITE (keypress) and BYE (hangup) packets from the phone.
#
# This approach bypasses Kamailio's exec module entirely and reads
# the same packets we confirmed work during tcpdump testing.
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(__file__))
import controller


def parse_line(line):
    """
    Parse a tcpdump output line and return the event type and key.

    tcpdump lines look like:
    14:00:58.959534 IP 192.168.10.2.5060 > 192.168.10.1.5060: SIP: INVITE sip:1@192.168.10.1 SIP/2.0
    14:00:59.057462 IP 192.168.10.2.5060 > 192.168.10.1.5060: SIP: BYE sip:1@192.168.10.1 SIP/2.0

    We only care about traffic FROM the phone (192.168.10.2)
    going TO Kamailio (192.168.10.1).
    """

    # Only process lines from the phone to the Pi
    if "192.168.10.2" not in line or "SIP:" not in line:
        return None, None

    # Detect INVITE — extract the dialed number from the URI
    if "SIP: INVITE" in line:
        try:
            sip_index = line.index("sip:")
            uri_part = line[sip_index + 4:]
            key = uri_part.split("@")[0].strip()
            if key.isdigit():
                return "keypress", key
        except (ValueError, IndexError):
            pass

    # Detect BYE — phone hung up
    if "SIP: BYE" in line:
        return "call_ended", None

    return None, None


def monitor():
    """
    Run tcpdump and process its output line by line in real time.
    Only watches port 5060 (SIP) traffic on the switch interface.
    """
    print("Starting SIP monitor on eth0 port 5060")

    cmd = [
        "tcpdump",
        "-i", "eth0",
        "-n",
        "-l",
        "port", "5060"
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    print("SIP monitor running — waiting for phone activity")

    controller.show_idle_screen()

    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            event, key = parse_line(line)

            if event == "keypress":
                ts = datetime.datetime.now().strftime('%H:%M:%S.%f')
                print(f"[{ts}] Keypress detected: {key}")
                controller.handle_keypress(key)

            elif event == "call_ended":
                ts = datetime.datetime.now().strftime('%H:%M:%S.%f')
                print(f"[{ts}] Hangup detected")
                controller.handle_hangup()

    except KeyboardInterrupt:
        print("SIP monitor stopped")

    finally:
        process.terminate()
        process.wait()


if __name__ == "__main__":
    monitor()