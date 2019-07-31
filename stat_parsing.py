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

logging.basicConfig(
	level=20,
	format='%(asctime)s %(levelname)s %(filename)s:%(lineno)d> %(message)s',
	datefmt='%Y/%m/%d %H:%M:%S'
)

def is_whitelisted(group):
	for stat in stat_whitelist:
		if stat in group['ids']:
			return True

	return False

def init():
	global trans_data
	global stat_whitelist

	with open('data/stat_translations.json', 'r') as f:
		trans_data = json.load(f)

	with open('stat_whitelist.json', 'r') as f:
		stat_whitelist = json.load(f)

	# apply stat whitelist
	trans_data = filter(is_whitelisted, trans_data)

	with open('whitelist_example.json', 'w') as f:
		json.dump(trans_data, f, sort_keys=True, indent=4)
 
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

class combined_stats_t:
	def __init__(self, trans_str, item=None, passive=None):
		if item is None and passive is None:
			raise ValueError("stat_t passed invalid args, must provide source item or passive")

		self.item = item
		self.passive = passive
		self.stats = []
		self.dict_cache = {}
		self.cache_valid = True

		self.parse_str(trans_str)

	def add(self, stat):
		self.stats.append(stat)
		self.cache_valid = False

	def parse_str(self, trans_block, item=1, passive=None):
		global trans_data

		# pad with new lines so we can easily detect each mod
		trans_block = "\n{}\n".format(trans_block)

		for translation_group in trans_data:
			ids = translation_group['ids']

			if u'dummy_stat_display_nothing' in ids:
				continue

			variations = translation_group['English']

			for variation in variations:
				pattern = "\n{}\n".format(variation['regex'])

				try:
					match = re.search(pattern, trans_block)
				except sre_constants.error as e:
					logging.error(pattern)
					raise e

				if match:
					if len(match.groups()) > 0:
						logging.debug("'{}' matches {} with values: {}".format(match.group(0).strip(), ids, match.groups()))
					else:
						logging.debug("'{}' matches {}".format(match.group(0).strip(), ids))

					# construct stat dict
					match_values = list(match.groups())
					stat_dict = {}

					for i in range(0, len(variation['format'])):
						stat_format = variation['format'][i]

						if stat_format == "ignore":
							stat_dict[ids[i]] = True
						else:
							stat_dict[ids[i]] = match_values.pop(0)


					stat = stat_t(match.group(0).strip(), stat_dict, item=item, passive=passive)
					self.add(stat)

					#logging.info(pattern)

					trans_block = re.sub(pattern.strip(), "", trans_block)

					#logging.info(trans_block)

		for match in re.finditer("[^\n]+", trans_block):
			logging.warn("Non-matched modifier: '{}'".format(match.group()))

	def build_cache(self):
		self.dict_cache = {}

		for stat in self.stats:
			for id, value in stat.dict.items():
				if id in self.dict_cache:
					if type(value) != type(self.dict_cache[id]):
						raise ValueError('cannot combine {} with {}'.format(type(value), type(self.dict_cache[i])))

					if type(value) == "int":
						self.dict_cache[id] += value
					else:
						self.dict_cache[id] = value or self.dict_cache[id]
				else:
					self.dict_cache[id] = value

		self.cache_valid = True

	def dict(self):
		if not self.cache_valid:
			self.build_cache()

		return self.dict_cache

class stat_t:
	def __init__(self, stat_str, stats, item=None, passive=None):
		if item is None and passive is None:
			raise ValueError("stat_t passed invalid args, must provide source item or passive")

		self.string = stat_str
		self.dict = stats
		self.item = item
		self.passive = passive

		logging.debug(self.dict)


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

signage isn't done right for this mod, need to recognize that the value is negative
WARNING:root:'40% reduced Soul Cost of Vaal Skills' matches [u'vaal_skill_soul_cost_+%'] with values: ('40',)
'''



#print(parse(test_mods))

start = time.time()

test_mods = """100% increased Global Critical Strike Chance
75% increased Critical Strike Chance for Spells
40% reduced Soul Cost of Vaal Skills
Can have multiple Crafted Modifiers
78% increased Fire Damage
Adds 13 to 160 Lightning Damage to Spells
21% chance to Ignite"""

cs = combined_stats_t(test_mods, item=1)

logging.info(cs.dict())

logging.info(time.time()-start)