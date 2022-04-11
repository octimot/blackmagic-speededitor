#!/usr/bin/env python3

"""
Simple mapping from Speed editor to Mackie controller (MCU) via MIDI.
Copyright (C) 2022 Ondrej Sindelar
Copyright (C) 2021 Sylvain Munaut <tnt@246tNt.com>
SPDX-License-Identifier: Apache-2.0
"""
import threading
from threading import Thread
from typing import List

import mido

from bmd import SpeedEditorKey, SpeedEditorLed, SpeedEditorJogLed, SpeedEditorJogMode, SpeedEditorHandler, SpeedEditor


class MackieHandler(SpeedEditorHandler):
    # virtual midi loop ports (loopMIDI)
    midi_in_device = 'mackieIn'
    midi_out_device = 'mackieOut'

    JOG = {
        SpeedEditorKey.SHTL: (SpeedEditorJogLed.SHTL, SpeedEditorJogMode.RELATIVE_2),
        SpeedEditorKey.JOG: (SpeedEditorJogLed.JOG, SpeedEditorJogMode.RELATIVE_2),
        SpeedEditorKey.SCRL: (SpeedEditorJogLed.SCRL, SpeedEditorJogMode.RELATIVE_2),
    }

    JOG_SPEED_FACTOR = {
        SpeedEditorKey.SHTL: 20,
        SpeedEditorKey.JOG: 15,
        SpeedEditorKey.SCRL: 1
    }

    ZOOM_REPEAT_TIME = 0.15

    MCU_JOG_CC = 0x3c
    MCU_STOP = 0x5D
    MCU_PLAY = 0x5E
    MCU_REC = 0x5F
    MCU_UP = 0x60
    MCU_DOWN = 0x61
    MCU_LEFT = 0x62
    MCU_RIGHT = 0x63
    MCU_ZOOM = 0x64
    MCU_SCRUB = 0x65

    ZOOM_KEYS = (SpeedEditorKey.IN, SpeedEditorKey.OUT, SpeedEditorKey.TRIM_IN, SpeedEditorKey.TRIM_OUT)

    def __init__(self, se):
        self.zoom_timer_on = False
        self.se = se
        self.keys = set()
        self.leds = 0
        self.se.set_leds(self.leds)
        self.play_state = False
        self.zoom_mode = False
        self.scrub_mode = False
        self.jog_unsent = 0
        self._set_jog_mode_for_key(SpeedEditorKey.JOG)
        device_name = self.find_device_in_list(self.midi_in_device, mido.get_output_names())
        self.midi_out = mido.open_output(device_name)
        device_name = self.find_device_in_list(self.midi_out_device, mido.get_input_names())
        self.midi_in = mido.open_input(device_name)
        thread = Thread(target=self.receive_thread)
        thread.start()

    def find_device_in_list(self, device, list):
        full_device = next((n for n in list if n.startswith(device)), None)
        if not full_device:
            raise RuntimeError(f"Device {device} not found in list {list}")
        return full_device

    def receive_thread(self):
        "Receive MCU midi events -> register current states"
        while True:
            msg = self.midi_in.receive()
            if msg.type == 'note_on':
                if msg.note == self.MCU_PLAY:
                    self.play_state = msg.velocity > 0
                if msg.note == self.MCU_ZOOM:
                    self.zoom_mode = msg.velocity > 0
                if msg.note == self.MCU_SCRUB:
                    self.scrub_mode = msg.velocity > 0

    def _set_jog_mode_for_key(self, key: SpeedEditorKey):
        if key not in self.JOG:
            return
        self.jog_mode = key
        self.se.set_jog_leds(self.JOG[key][0])
        self.se.set_jog_mode(self.JOG[key][1])
        if (key == SpeedEditorKey.SHTL) == (not self.scrub_mode):
            self.send_midi_note(self.MCU_SCRUB)

    def jog(self, mode: SpeedEditorJogMode, value):
        # increments come in multiples of 360
        value //= 360
        self.jog_unsent += value

        speed_factor = self.JOG_SPEED_FACTOR[self.jog_mode]
        value_to_send = self.jog_unsent // speed_factor
        if value_to_send == 0:
            return
        # remaining sub-step wheel rotation - save for later
        self.jog_unsent -= value_to_send * speed_factor
        self.send_midi_jog_cc(value_to_send)

    def key(self, keys: List[SpeedEditorKey]):
        kl = ', '.join([k.name for k in keys])
        if not kl:
            kl = 'None'
        print(f"Keys held: {kl:s}")

        keys_set = set(keys)
        released = self.keys - keys_set
        pressed = keys_set - self.keys
        self.keys = keys_set
        for k in released:
            self.key_released(k)

        for k in pressed:
            self.key_pressed(k)

    def key_released(self, k):
        pass

    def key_pressed(self, k):
        # Select jog mode
        self._set_jog_mode_for_key(k)

        # Toggle leds
        self.leds ^= getattr(SpeedEditorLed, k.name, 0)
        self.se.set_leds(self.leds)

        # stop/play -> send play or stop depending on current the state
        if k == SpeedEditorKey.STOP_PLAY:
            self.send_midi_note(self.MCU_STOP if self.play_state else self.MCU_PLAY)
        # red button -> record
        if k == SpeedEditorKey.FULL_VIEW:
            self.send_midi_note(self.MCU_REC)
        if k in self.ZOOM_KEYS:
            self.zoom_handle_keys()

    def send_midi_note(self, note):
        self.midi_out.send(mido.Message('note_on', note=note, velocity=127))

    def send_midi_jog_cc(self, shift: int):
        abs_val_full = abs(shift)
        while abs_val_full > 0:
            abs_val = abs_val_full
            if abs_val > 63:
                abs_val = 63
            sign = int(shift < 0) << 6
            val = abs_val | sign
            self.midi_out.send(mido.Message('control_change', control=self.MCU_JOG_CC, value=val))
            abs_val_full -= abs_val

    def set_zoom_mode(self):
        if not self.zoom_mode:
            self.send_midi_note(self.MCU_ZOOM)

    def zoom_repeat(self):
        self.zoom_timer_on = False
        self.zoom_handle_keys()

    def set_zoom_timer(self):
        if not self.zoom_timer_on:
            self.zoom_timer_on = True
            zoom_timer = threading.Timer(self.ZOOM_REPEAT_TIME, self.zoom_repeat)
            zoom_timer.start()

    def zoom_handle_keys(self):
        zoom_pressed = False
        if any(k in self.keys for k in self.ZOOM_KEYS):
            self.set_zoom_mode()
            zoom_pressed = True
        if SpeedEditorKey.IN in self.keys:
            self.send_midi_note(self.MCU_RIGHT)
        if SpeedEditorKey.OUT in self.keys:
            self.send_midi_note(self.MCU_LEFT)
        if SpeedEditorKey.TRIM_IN in self.keys:
            self.send_midi_note(self.MCU_DOWN)
        if SpeedEditorKey.TRIM_OUT in self.keys:
            self.send_midi_note(self.MCU_UP)
        if zoom_pressed:
            self.set_zoom_timer()


if __name__ == '__main__':
    se = SpeedEditor()
    se.authenticate()
    se.set_handler(MackieHandler(se))

    while True:
        se.poll()
