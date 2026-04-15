import asyncio
import json
import sys
import os

# Add the controller folder to the path so we can import controller.py
sys.path.insert(0, os.path.dirname(__file__))

import controller
from config import KAMAILIO_HOST, KAMAILIO_PORT, KAMAILIO_EVAPI_PORT

# ---------------------------------------------------------------------------
# sip_listener.py
#
# This file is the bridge between Kamailio (the SIP server) and the
# Python controller. It connects to Kamailio's evapi socket and listens
# for JSON events sent whenever something happens on the phone:
#
#   {"event": "call_started"}  — participant picked up the handset
#   {"event": "keypress", "key": "1"}  — participant pressed a key
#   {"event": "call_ended"}  — participant hung up
#
# When an event arrives, this file routes it to the correct function
# in controller.py which handles the actual video playback logic.
#
# This file runs continuously in the background as long as the exhibit
# is running. If the connection to Kamailio drops, it automatically
# retries every 5 seconds so the exhibit recovers without intervention.
# ---------------------------------------------------------------------------

# How long to wait before retrying if connection to Kamailio drops
RETRY_DELAY_SECONDS = 5


async def handle_event(raw_message):
    """
    Parse a raw JSON message from Kamailio and route it to the
    correct controller function.

    Expected message formats:
      {"event": "call_started"}
      {"event": "keypress", "key": "3"}
      {"event": "call_ended"}
    """
    try:
        data = json.loads(raw_message.strip())
        event = data.get("event")

        if not event:
            print(f"Received message with no event field: {data}")
            return

        print(f"Event received: {event}")

        if event == "call_started":
            # Participant picked up the handset
            # Idle screen is already showing so nothing visual needed
            # If a previous video is somehow still playing, stop it
            if controller.current_video is not None:
                print("Video was still playing on pickup — stopping it")
                controller.stop_video(return_to_idle=True)
            print("Handset picked up — waiting for keypress")

        elif event == "keypress":
            # Participant pressed a key — route to controller
            key = data.get("key", "").strip()
            if key:
                print(f"Routing keypress: {key}")
                controller.handle_keypress(key)
            else:
                print("Keypress event received but no key value found")

        elif event == "call_ended":
            # Participant hung up — stop video and return to idle
            print("Handset hung up — stopping video")
            controller.handle_hangup()

        else:
            print(f"Unknown event type received: {event}")

    except json.JSONDecodeError as e:
        print(f"Could not parse message as JSON: {raw_message!r} — {e}")

    except Exception as e:
        print(f"Error handling event: {e}")


async def listen_to_kamailio():
    """
    Connect to Kamailio's evapi socket and listen for events.
    Kamailio pushes a JSON message every time something happens on the phone.
    """
    print(f"Connecting to Kamailio evapi at {KAMAILIO_HOST}:{KAMAILIO_EVAPI_PORT}")

    reader, writer = await asyncio.open_connection(KAMAILIO_HOST, KAMAILIO_EVAPI_PORT)
    print("Connected to Kamailio — listening for phone events")

    try:
        while True:
            line = await reader.readline()

            if not line:
                print("Kamailio closed the connection")
                break

            message = line.decode("utf-8").strip()
            if message:
                await handle_event(message)

    except asyncio.CancelledError:
        pass

    except Exception as e:
        print(f"Connection error: {e}")

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    """
    Main loop — connects to Kamailio and automatically reconnects
    if the connection drops. The exhibit recovers on its own without
    any manual intervention.
    """
    print("SIP listener starting up")

    while True:
        try:
            await listen_to_kamailio()
        except ConnectionRefusedError:
            print(f"Could not connect to Kamailio — retrying in {RETRY_DELAY_SECONDS}s")
            print("Make sure Kamailio is running: sudo systemctl status kamailio")
        except Exception as e:
            print(f"Unexpected error: {e} — retrying in {RETRY_DELAY_SECONDS}s")

        await asyncio.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())