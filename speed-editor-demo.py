#!/usr/bin/env python3

# Copyright (C) 2021 Sylvain Munaut <tnt@246tNt.com>
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from typing import List

from bmd import SpeedEditorKey, SpeedEditorLed, SpeedEditorJogLed, SpeedEditorJogMode, SpeedEditorHandler, SpeedEditor

from pynput.keyboard import Key, Controller

class DemoHandler(SpeedEditorHandler):
	JOG = {
		SpeedEditorKey.SHTL: (SpeedEditorJogLed.SHTL, SpeedEditorJogMode.ABSOLUTE_DEADZERO),
		SpeedEditorKey.JOG: (SpeedEditorJogLed.JOG, SpeedEditorJogMode.RELATIVE_2),
		SpeedEditorKey.SCRL: (SpeedEditorJogLed.SCRL, SpeedEditorJogMode.RELATIVE_2),
	}

	def __init__(self, se):
		self.se = se
		self.keys = []
		self.leds = 0
		self.se.set_leds(self.leds)
		self._set_jog_mode_for_key(SpeedEditorKey.SCRL)

		self.keyboard = Controller()

	def _set_jog_mode_for_key(self, key: SpeedEditorKey):
		if key not in self.JOG:
			return
		self.se.set_jog_leds(self.JOG[key][0])
		self.se.set_jog_mode(self.JOG[key][1])

	def jog(self, mode: SpeedEditorJogMode, value):
		print(f"Jog mode {mode:d} : {value:d}")

		# example
		# when the jog wheel is turned, we're simulating the press and release of left/right keys
		if value > 0:
			self.keyboard.press(Key.right)
			self.keyboard.release(Key.right)
		else:
			self.keyboard.press(Key.left)
			self.keyboard.release(Key.left)


	def key(self, keys: List[SpeedEditorKey]):
		# Debug message
		kl = ', '.join([k.name for k in keys])
		if not kl:
			kl = 'None'
		print(f"Keys held: {kl:s}")

		# Find keys being released and toggle led if there is one
		for k in self.keys:
			if k not in keys:
				# Select jog mode
				self._set_jog_mode_for_key(k)

				# Toggle leds
				self.leds ^= getattr(SpeedEditorLed, k.name, 0)
				self.se.set_leds(self.leds)

		self.keys = keys

		# example
		# pressing CAM1, will press the '1' key on the keyboard
		if kl == 'CAM1':
			self.keyboard.press('1')
			self.keyboard.release('1')



	def battery(self, charging: bool, level: int):
		print(f"Battery {level:d} %{' and charging' if charging else '':s}")


if __name__ == '__main__':
	print(datetime.now())
	se = SpeedEditor()
	timeout = se.authenticate()
	print(f"Timeout: {timeout:d}")
	se.set_handler(DemoHandler(se))

	while True:
		se.poll()
