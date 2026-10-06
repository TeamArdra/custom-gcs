"""Send the mission START (or ABORT) command over the MicroLR900 telemetry
radio instead of the Wi-Fi/rosbridge link.

Laptop --USB--> MicroLR900 ))) MicroLR900 --TELEM--> Pixhawk --Ethernet-->
mavros --> onboard-autonomy's telem_command_bridge_node --> /gcs/command.

The Jetson side treats a radio START exactly like a GCS START (same
command_node validation, same mission_state_node arm path). Wire format is
defined in onboard-autonomy's nidar_autonomy/telem_command_codec.py; the
constants below must match it.

Usage (Windows):
    pip install pymavlink pyserial
    python tools/telem_command.py --port COM5

Then type `start` (or `abort`) at the prompt. Keep the tool open for the
whole flight: it sends a GCS heartbeat at 1 Hz, and if ArduPilot's
FS_GCS_ENABLE is set, closing it while armed triggers the GCS failsafe.
"""

from __future__ import annotations

import argparse
import random
import threading
import time

from pymavlink import mavutil

# Must match onboard-autonomy/nidar_autonomy/nidar_autonomy/telem_command_codec.py
MAV_CMD_USER_1 = 31010
NIDAR_START = 1.0
NIDAR_ABORT = 2.0
NIDAR_MAGIC = 4242.0
COMMAND_PARAM = {"start": NIDAR_START, "abort": NIDAR_ABORT}

AUTOPILOT_COMPID = 1


class Link:
    def __init__(self, port: str, baud: int, target_sys: int, target_comp: int) -> None:
        self.conn = mavutil.mavlink_connection(
            port, baud=baud, source_system=255, source_component=190
        )
        self.target_sys = target_sys
        self.target_comp = target_comp
        self._send_lock = threading.Lock()
        self._acks: list = []
        self._ack_event = threading.Event()
        self.armed = None
        self.mode = None
        self.last_fcu_heartbeat = 0.0
        self._stop = threading.Event()

    def start_threads(self) -> None:
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            with self._send_lock:
                self.conn.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
                )
            self._stop.wait(1.0)

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            msg = self.conn.recv_match(type=["HEARTBEAT", "COMMAND_ACK"], blocking=True, timeout=0.5)
            if msg is None:
                continue
            src_sys, src_comp = msg.get_srcSystem(), msg.get_srcComponent()
            if msg.get_type() == "HEARTBEAT":
                if src_sys == self.target_sys and src_comp == AUTOPILOT_COMPID:
                    self.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    self.mode = mavutil.mode_string_v10(msg)
                    self.last_fcu_heartbeat = time.monotonic()
            elif (
                msg.command == MAV_CMD_USER_1
                and src_sys == self.target_sys
                and src_comp == self.target_comp
            ):
                self._acks.append(msg)
                self._ack_event.set()

    def fcu_alive(self) -> bool:
        return time.monotonic() - self.last_fcu_heartbeat < 3.0

    def send_command(self, command: str, retries: int, interval: float):
        """Send until the Jetson ACKs. The same nonce is reused on every
        resend, so the Jetson forwards it to /gcs/command only once."""
        nonce = random.randint(1, 1_000_000)
        for attempt in range(1, retries + 1):
            self._ack_event.clear()
            with self._send_lock:
                self.conn.mav.command_long_send(
                    self.target_sys, self.target_comp, MAV_CMD_USER_1, 0,
                    COMMAND_PARAM[command], nonce, NIDAR_MAGIC, 0, 0, 0, 0,
                )
            print(f"  -> sent {command.upper()} (nonce {nonce}, attempt {attempt}/{retries})")
            if self._ack_event.wait(interval):
                return self._acks[-1]
        return None


def _status(link: Link) -> str:
    if not link.fcu_alive():
        return "Pixhawk: NO HEARTBEAT (check radio)"
    return f"Pixhawk: {'ARMED' if link.armed else 'DISARMED'}, mode {link.mode}"


def _wait_for_arm_state(link: Link, want_armed: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if link.armed == want_armed:
            return True
        time.sleep(0.2)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", required=True, help="radio serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=57600)
    parser.add_argument("--target-sys", type=int, default=1, help="mavros system_id on the Jetson")
    parser.add_argument("--target-comp", type=int, default=240, help="mavros component_id on the Jetson")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--ack-timeout", type=float, default=1.0)
    args = parser.parse_args()

    link = Link(args.port, args.baud, args.target_sys, args.target_comp)
    link.start_threads()
    print(f"Opened {args.port} @ {args.baud}; waiting for Pixhawk heartbeat...")
    for _ in range(50):
        if link.fcu_alive():
            break
        time.sleep(0.1)
    print(_status(link))
    print("Commands: start | abort | status | quit")

    try:
        while True:
            line = input("> ").strip().lower()
            if line in ("quit", "exit", "q"):
                if link.armed:
                    print("Vehicle is ARMED -- type `quit` again to really exit.")
                    if input("> ").strip().lower() not in ("quit", "exit", "q"):
                        continue
                break
            if line == "status" or line == "":
                print(_status(link))
                continue
            if line not in COMMAND_PARAM:
                print("Unknown command. Use: start | abort | status | quit")
                continue
            if line == "start":
                confirm = input(f"{_status(link)}. START will ARM the vehicle. Type START to confirm: ")
                if confirm.strip() != "START":
                    print("Cancelled.")
                    continue

            ack = link.send_command(line, args.retries, args.ack_timeout)
            if ack is None:
                print(f"  !! No ACK from Jetson {args.target_sys}/{args.target_comp} "
                      f"after {args.retries} tries. Check bridge node / component id.")
                continue
            print(f"  <- Jetson ACKed {line.upper()} (result {ack.result})")
            want_armed = line == "start"
            if _wait_for_arm_state(link, want_armed, timeout=5.0):
                print(f"  Pixhawk now {'ARMED' if want_armed else 'DISARMED'}.")
            else:
                print(f"  !! Jetson accepted it but Pixhawk did not report "
                      f"{'ARMED' if want_armed else 'DISARMED'} within 5 s. {_status(link)}")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        link.stop()


if __name__ == "__main__":
    main()
