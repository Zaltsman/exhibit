import sys
import os

# ---------------------------------------------------------------------------
# handle_event.py
#
# This script is called directly by Kamailio via the exec module
# whenever something happens on the phone. It receives the event
# as command line arguments and routes it to the correct controller function.
#
# Kamailio calls it like this:
#   python3 handle_event.py keypress 1
#   python3 handle_event.py call_ended
#
# This approach is simpler and more reliable than the evapi socket approach
# because Kamailio just runs a script — no subscription handshake needed.
#
# The script runs quickly and exits — it is not a long-running process.
# ---------------------------------------------------------------------------

# Add the controller folder to the path so we can import controller.py
sys.path.insert(0, os.path.dirname(__file__))

import controller


def main():
    # Get the event type from the first command line argument
    # sys.argv[0] is the script name, sys.argv[1] is the event
    if len(sys.argv) < 2:
        print("Error: no event type provided")
        print("Usage: python3 handle_event.py <event> [key]")
        sys.exit(1)

    event = sys.argv[1]

    if event == "keypress":
        # Get the key from the second argument
        if len(sys.argv) < 3:
            print("Error: keypress event requires a key argument")
            sys.exit(1)

        key = sys.argv[2]
        print(f"Handling keypress: {key}")
        controller.handle_keypress(key)

    elif event == "call_ended":
        # Phone was hung up — stop video and return to idle
        print("Handling call_ended — stopping video")
        controller.handle_hangup()

    else:
        print(f"Unknown event: {event}")
        sys.exit(1)


if __name__ == "__main__":
    main()