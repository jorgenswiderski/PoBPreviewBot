# Python
import re
import logging
import json
import time
import sre_constants

# 3rd Party

# Self

'''
FIXME

This will ONLY parse mods on items because stat_translations.json only includes translation for stats found on items.
For more translations, namely passive skills, I'll need to also loadup these files in a similar manner:
 - RePoE/stat_translations/passive_skill.json
 - RePoE/stat_translations/passive_skill_aura.json

See here for more info:
https://github.com/brather1ng/RePoE/blob/master/docs/stat_translations.md
'''

def init():
	global trans_data

	with open('data/stat_translations.json', 'r') as f:
		trans_data = json.load(f)

	for translation_group in trans_data:
		ids = translation_group['ids']
		variations = translation_group['English']

		for variation in variations:
			variation['regex'] = make_regex(variation)
			logging.debug('"{}" ==> "{}"'.format(variation['string'], variation['regex']))

def escape(s):
	if len(s) > 0 and s[0] == '+':
		s = '\\' + s

	s = re.sub('\?', '\?', s)

	return s

# returns a list of stats

def make_regex(variation):
	# base string
	vstr = escape(variation['string'])

	for i in range(0, len(variation['format'])):
		needle = "\{" + str(i) + "}"
		stat_format = variation['format'][i]

		if stat_format == "ignore":
			continue

		replacement = None

		if stat_format == "#":
			replacement = "(\d+)"
		elif stat_format == "+#":
			replacement = "[+-](\d+)"
		elif stat_format == "#%":
			replacement = "(\d+)%"
		elif stat_format == "+#%":
			replacement = "[+-](\d+)%"
		else:
			raise ValueError("unhandled format value")

		logging.debug(needle)
		logging.debug(replacement)
		logging.debug(vstr)

		vstr = re.sub(needle, replacement, vstr)

	return vstr


def parse(trans_block, item=1, passive=None):
	stats = []

	for translation_group in trans_data:
		ids = translation_group['ids']

		if u'dummy_stat_display_nothing' in ids:
			continue

		variations = translation_group['English']

		for variation in variations:
			pattern = variation['regex']

			try:
				match = re.search(pattern, trans_block)
			except sre_constants.error as e:
				logging.warn(pattern)
				raise e

			if match:
				if len(match.groups()) > 0:
					logging.warn("'{}' matches {} with values: {}".format(match.group(0), ids, match.groups()))
				else:
					logging.warn("'{}' matches {}".format(match.group(0), ids))

				stat = stat_t(match.group(0), ids, match.groups(), item=item, passive=passive)
				stats.append(stat)

				trans_block = re.sub(pattern, "", trans_block)

	return stats

class stat_t:
	def __init__(self, stat_str, stat_id, values, item=None, passive=None):
		if item is None and passive is None:
			raise ValueError("stat_t passed invalid args, must provide source item or passive")

		self.string = stat_str
		self.id = stat_id
		self.values = values
		self.item = item
		self.passive = passive


init()
'''
test_mods = """Sockets cannot be modified
+1 to Level of Socketed Gems
100% increased Global Defences
You can only Socket Corrupted Gems in this item
Zealot's Oath"""
'''

'''
FIXME: 

this mod is mapped incorrectly
WARNING:root:'Adds 13 to 160 Lightning Damage' matches [u'global_minimum_added_lightning_damage', u'global_maximum_added_lightning_damage'] with values: ('13', '160')

signage isn't done right for this mod, need to recognize that the value is negative
WARNING:root:'40% reduced Soul Cost of Vaal Skills' matches [u'vaal_skill_soul_cost_+%'] with values: ('40',)
'''

test_mods = """
100% increased Global Critical Strike Chance
75% increased Critical Strike Chance for Spells
40% reduced Soul Cost of Vaal Skills
Can have multiple Crafted Modifiers
78% increased Fire Damage
Adds 13 to 160 Lightning Damage to Spells
21% chance to Ignite
"""

#print(parse(test_mods))

start = time.time()

logging.warn(parse(test_mods))

logging.warn(time.time()-start)