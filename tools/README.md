# tools/

Development and field tooling that isn't part of the GCS application itself.

- `laptop_rosbridge_smoke_test.py` — checks the laptop can reach the
  Jetson's rosbridge over Wi-Fi.
- `telem_command.py` — sends mission START/ABORT over the MicroLR900
  telemetry radio (no Wi-Fi needed). See `docs/COMMUNICATION.md` §6.

## telem_command.py

Needs the Jetson running `telem_command_bridge_node` (onboard-autonomy).

```powershell
pip install pymavlink pyserial
python tools/telem_command.py --port COM5            # 57600 baud default
python tools/telem_command.py --port COM5 --target-comp 191   # if mavros' component_id isn't 240
```

At the `>` prompt: `status`, `start` (asks you to type START to confirm),
`abort`, `quit`. It shows the Pixhawk's armed state straight from the
radio, so you can see the START actually armed the vehicle.

Keep it open for the whole flight: it sends a GCS heartbeat at 1 Hz, and
if the Pixhawk has `FS_GCS_ENABLE` set, closing it while armed triggers
the GCS failsafe.
