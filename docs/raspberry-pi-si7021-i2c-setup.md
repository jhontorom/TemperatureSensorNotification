# Raspberry Pi 5: SparkFun Si7021 I2C Setup

This guide prepares Raspberry Pi OS to use a SparkFun Si7021 temperature and humidity sensor on I2C bus 1.

## 1. Wire the sensor

Shut down and unplug the Raspberry Pi before changing wires.

| Si7021 breakout pin | Raspberry Pi 5 header pin | Raspberry Pi label |
| --- | ---: | --- |
| `VCC` | Physical pin 1 or 17 | 3.3V |
| `GND` | Physical pin 6 | GND |
| `SDA` | Physical pin 3 | GPIO 2 / SDA |
| `SCL` | Physical pin 5 | GPIO 3 / SCL |

> **Important:** Power the SparkFun Si7021 from **3.3V only**. Do not connect its `VCC` pin to the Pi's 5V pins (physical pins 2 or 4).

The SparkFun breakout includes its own I2C pull-up resistors, so no additional resistors are required for this single sensor.

## 2. Install I2C tools and enable I2C

Connect to the Pi over SSH, then run:

```bash
sudo apt update
sudo apt install -y i2c-tools python3-venv
sudo raspi-config nonint do_i2c 0
sudo reboot
```

The last command disconnects SSH while the Pi restarts. Wait about one minute, then reconnect.

## 3. Confirm the Pi can see the sensor

```bash
ls -l /dev/i2c-1
sudo i2cdetect -y 1
```

The scan should show `40` at I2C address `0x40`:

```text
40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

## 4. Set up the project’s Python environment

Run these commands from the project directory. Create the virtual environment only if `.venv` does not already exist.

```bash
cd /home/ai_jhontoro/Projects/RoomTemperature
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## 5. Run the sensor check

```bash
cd /home/ai_jhontoro/Projects/RoomTemperature
.venv/bin/python -m room_monitor.cli_sensor_check
```

Expected output resembles:

```text
Temperature: 25.94 C / 78.69 F
Humidity: 49.99 %
```

The actual values will vary with the room conditions.

## 6. Run the automated tests

```bash
cd /home/ai_jhontoro/Projects/RoomTemperature
.venv/bin/pytest -q
```

## Troubleshooting

### `i2cdetect` does not show `40`

1. Turn off the Pi and check all four wires.
2. Confirm `VCC` uses 3.3V and that the ground wire is connected.
3. Confirm the data wires are not swapped: SDA is physical pin 3; SCL is physical pin 5.
4. Boot the Pi and repeat the address scan.

### `Remote I/O error`

First confirm the sensor is detected:

```bash
sudo i2cdetect -y 1
```

If `40` appears but a sensor read fails, power off the Pi, reseat the wires and sensor, then boot and retry the sensor check. Do not use generic register-dump commands with the Si7021: it does not expose ordinary register-address reads. The application uses its required raw I2C measurement sequence.

For a focused communication check, request the Si7021 user register:

```bash
sudo i2ctransfer -y 1 w1@0x40 0xe7 r1
```

This should return one hexadecimal byte. If it produces `Remote I/O error`, the issue is electrical wiring, power, the sensor board, or a connection rather than the Python application.

## References

- [Raspberry Pi: Enable I2C](https://www.raspberrypi.com/documentation/computers/configuration.html)
- [SparkFun Si7021 hookup guide](https://learn.sparkfun.com/tutorials/si7021-humidity-and-temperature-sensor-hookup-guide/all)
