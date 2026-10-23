"""Deterministic PCA9685, I2C, and cancellation fakes for servo tests."""

from __future__ import annotations

import threading
from copy import deepcopy
from types import ModuleType, SimpleNamespace

DEFAULT_CONFIG = {
    "CONTROLS": {
        "enabled": False,
        "voicemovement": True,
        "ventilate": False,
        "swap_turn_directions": False,
    },
    "SERVO": {
        "arms_present": True,
        "leftUpHeight": 220,
        "leftDownHeight": 460,
        "perfectLeftHeightOffset": 7,
        "rightUpHeight": 460,
        "rightDownHeight": 220,
        "perfectRightHeightOffset": 9,
        "forwardLeftLeg": 160,
        "backLeftLeg": 460,
        "perfectLeftLegOffset": 5,
        "forwardRightLeg": 460,
        "backRightLeg": 160,
        "perfectRightLegOffset": -4,
        "leftMainMin": 550,
        "leftMainMax": 50,
        "leftMainOffset": -30,
        "leftForarmMin": 500,
        "leftForarmMax": 230,
        "leftForearmOffset": 25,
        "leftHandMin": 420,
        "leftHandMax": 300,
        "leftHandOffset": 0,
        "rightMainMin": 50,
        "rightMainMax": 550,
        "rightMainOffset": 0,
        "rightForarmMin": 230,
        "rightForarmMax": 500,
        "rightForearmOffset": -55,
        "rightHandMin": 300,
        "rightHandMax": 420,
        "rightHandOffset": 0,
    },
}


class FakeStopEvent:
    """Event whose waits return immediately and can trigger cancellation."""

    def __init__(self):
        self._set = False
        self._lock = threading.Lock()
        self.wait_calls = 0
        self.cancel_after_waits = None

    def set(self):
        with self._lock:
            self._set = True

    def clear(self):
        with self._lock:
            self._set = False
            self.wait_calls = 0

    def is_set(self):
        with self._lock:
            return self._set

    def wait(self, timeout=None):
        del timeout
        with self._lock:
            self.wait_calls += 1
            if (
                self.cancel_after_waits is not None
                and self.wait_calls >= self.cancel_after_waits
            ):
                self._set = True
            return self._set


class FakeI2C:
    def __init__(self, backend):
        self.backend = backend
        self.deinitialized = False

    def deinit(self):
        self.deinitialized = True


class FakeChannel:
    def __init__(self, controller, index):
        self.controller = controller
        self.index = index
        self._duty_cycle = 0

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        if self.controller.deinitialized:
            raise OSError("controller is deinitialized")
        backend = self.controller.backend
        backend.write_attempts.append((self.controller, self.index, value))
        if self.index == 15 and backend.probe_failures > 0:
            backend.probe_failures -= 1
            raise OSError(121, "simulated probe failure")
        failures = backend.write_failures.get(self.index, 0)
        if failures > 0:
            backend.write_failures[self.index] = failures - 1
            raise OSError(121, "simulated PWM failure")
        self._duty_cycle = value
        backend.successful_writes.append((self.controller, self.index, value))


class FakePCA9685:
    def __init__(self, backend, i2c, address):
        self.backend = backend
        self.i2c = i2c
        self.address = address
        self.frequency = None
        self.deinitialized = False
        self.channels = [FakeChannel(self, index) for index in range(16)]

    def deinit(self):
        self.deinitialized = True


class FakeServoBackend:
    """Factory and recorder injected into module_servoctl."""

    def __init__(self):
        self.buses = []
        self.controllers = []
        self.write_attempts = []
        self.successful_writes = []
        self.write_failures = {}
        self.probe_failures = 0

    def create_i2c(self, scl, sda):
        del scl, sda
        bus = FakeI2C(self)
        self.buses.append(bus)
        return bus

    def create_pca(self, i2c, address=0x40):
        controller = FakePCA9685(self, i2c, address)
        self.controllers.append(controller)
        return controller

    @property
    def latest_controller(self):
        return self.controllers[-1] if self.controllers else None

    def all_outputs_disabled(self, controller=None):
        controller = controller or self.latest_controller
        return controller is not None and all(
            channel.duty_cycle == 0 for channel in controller.channels
        )


def make_config():
    return deepcopy(DEFAULT_CONFIG)


def install_import_fakes(config, messages):
    """Install only the import-time dependencies absent on development PCs."""
    import sys

    board = ModuleType("board")
    board.SCL = object()
    board.SDA = object()

    busio = ModuleType("busio")
    busio.I2C = lambda scl, sda: None

    pca_module = ModuleType("adafruit_pca9685")
    pca_module.PCA9685 = lambda i2c, address=0x40: None

    config_module = ModuleType("modules.module_config")
    config_module._config_cache = None
    config_module.load_config = lambda: config

    message_module = ModuleType("modules.module_messageQue")
    message_module.queue_message = messages.append

    cpu_module = ModuleType("modules.module_cputemp")
    cpu_module.is_ventilating = lambda: False
    cpu_module.record_movement = lambda: None

    sys.modules["board"] = board
    sys.modules["busio"] = busio
    sys.modules["adafruit_pca9685"] = pca_module
    sys.modules["modules.module_config"] = config_module
    sys.modules["modules.module_messageQue"] = message_module
    sys.modules["modules.module_cputemp"] = cpu_module

    return SimpleNamespace(
        board=board,
        busio=busio,
        pca_module=pca_module,
        config_module=config_module,
    )
