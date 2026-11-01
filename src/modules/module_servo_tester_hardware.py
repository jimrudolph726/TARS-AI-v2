"""Exclusive PCA9685 session used by the standalone servo tester."""

from __future__ import annotations

from dataclasses import dataclass

from modules.module_servo_hardware import close_quietly


@dataclass
class ServoTesterHardwareSession:
    servoctl: object | None = None
    i2c: object | None = None
    pca: object | None = None
    error: str = ""

    @property
    def connected(self) -> bool:
        return self.servoctl is not None and self.pca is not None

    def connect(self) -> bool:
        candidate_i2c = None
        candidate_pca = None
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685
            import modules.module_servoctl as servoctl

            candidate_i2c = busio.I2C(board.SCL, board.SDA)
            candidate_pca = PCA9685(candidate_i2c, address=0x40)
            candidate_pca.frequency = 50
            candidate_pca.channels[15].duty_cycle = 0

            servoctl._i2c = candidate_i2c
            servoctl.pca = candidate_pca
            servoctl._channels_initialized.clear()
            if not servoctl.disable_all_servos():
                raise RuntimeError("PCA9685 outputs could not be confirmed off")

            self.servoctl = servoctl
            self.i2c = candidate_i2c
            self.pca = candidate_pca
            self.error = ""
            return True
        except Exception as exc:
            close_quietly(candidate_pca)
            close_quietly(candidate_i2c)
            self.servoctl = None
            self.i2c = None
            self.pca = None
            self.error = str(exc)
            return False

    def cleanup(self, timeout: float = 6.0) -> None:
        if self.servoctl is not None:
            self.servoctl.cleanup(timeout=timeout)
        else:
            close_quietly(self.pca)
            close_quietly(self.i2c)
        self.servoctl = None
        self.i2c = None
        self.pca = None
