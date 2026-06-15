# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Smoke tests for the Vb1940Emulator Python binding additions
(set_eeprom_data + VB1940_EEPROM_REGION_BYTES).

These tests verify only that the pybind11 layer accepts the various Python
buffer types we expect callers to pass. The full runtime semantics
(zero-pad, clamp, OOB bounds, 24LCxx wire protocol, etc.) are covered by
the C++ gtest suite in tests/vb1940_emulator_test.cpp -- duplicating them
in Python would require exposing i2c_transaction as a Python-friendly
function, which is outside the scope of this patch.

The tests import the pybind11 extension module (_emulation_sensors) directly
rather than going through `hololink.emulation.sensors`. This keeps the smoke
test focused on the new symbols and avoids depending on the rest of the
hololink package being importable in the local test environment.
"""

import importlib.util
import os
import pathlib
import sys

import pytest


def _load_so(pattern, mod_name):
    """Locate a single matching .so under PYTHONPATH and import it as `mod_name`."""
    matches = []
    for root in os.environ.get("PYTHONPATH", "").split(":"):
        if not root:
            continue
        matches.extend(pathlib.Path(root).rglob(pattern))
    if not matches:
        pytest.skip(f"{pattern} extension not found on PYTHONPATH")
    so_path = matches[0]
    spec = importlib.util.spec_from_file_location(mod_name, so_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[mod_name] = mod
    return mod


def _load_extension():
    # `_emulation_sensors` references `I2CPeripheral` from `_emulation` as a
    # pybind11 base type, so the base module must be imported first to register
    # the type. We bypass the `hololink` package's __init__.py chain because
    # one of the two upstream emulator __init__.py variants ships a broken
    # `from ._emulation import _emulation` line, which is unrelated to this
    # patch and would require an unrelated upstream fix to clear.
    _load_so("_emulation.cpython*.so", "_emulation")
    return _load_so("_emulation_sensors.cpython*.so", "_emulation_sensors")


@pytest.fixture(scope="module")
def hemu():
    return _load_extension()


def test_constant_is_exported_and_correct(hemu):
    assert hemu.VB1940_EEPROM_REGION_BYTES == 256


def test_set_eeprom_data_accepts_bytes(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(b"\x01\x02\x03\x04")


def test_set_eeprom_data_accepts_bytearray(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(bytearray(b"\xde\xad\xbe\xef"))


def test_set_eeprom_data_accepts_memoryview(hemu):
    emu = hemu.Vb1940Emulator()
    backing = bytearray(b"\x10" * 32)
    emu.set_eeprom_data(memoryview(backing))


def test_set_eeprom_data_handles_full_region(hemu):
    emu = hemu.Vb1940Emulator()
    blob = bytes(i % 256 for i in range(hemu.VB1940_EEPROM_REGION_BYTES))
    assert len(blob) == hemu.VB1940_EEPROM_REGION_BYTES
    emu.set_eeprom_data(blob)


def test_set_eeprom_data_handles_short_payload(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(b"\x01\x02\x03\x04\x05\x06\x07\x08")


def test_set_eeprom_data_handles_oversized_payload(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(b"\xab" * (hemu.VB1940_EEPROM_REGION_BYTES * 2))


def test_set_eeprom_data_handles_empty_payload(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(b"")


def test_reset_after_set_eeprom_data_does_not_crash(hemu):
    emu = hemu.Vb1940Emulator()
    emu.set_eeprom_data(b"\x55" * 64)
    emu.reset()
