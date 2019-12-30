# Python
import re
import logging
import json
import time
import sre_constants
import glob

# 3rd Party

# Self
import logger

def init_support_gem_stat_map(support_gem_ids):
	global support_gem_map

	support_gem_map = {}

	with open('data/mods.json', 'r') as f:
		mod_data = json.load(f)

	for mod_id, mod_dict in mod_data.items():
		for stat in mod_dict['stats']:
			if stat['id'] in support_gem_ids:

				key = stat['id']
				values = []

				for effect in mod_dict['grants_effects']:
					values.append(effect['granted_effect_id'].encode('utf-8'))

				support_gem_map[key] = values
				logging.log(logger.DEBUG_ALL, "Support gem stat {} mapped to {}".format(key, values))

				support_gem_ids.remove(key)

def init_keystone_stat_map(keystone_ids):
	global keystone_map

	keystone_map = {}

	for group in trans_data:
		for id in group['ids']:
			if id in keystone_ids:
				key = group['English'][0]['string']
				keystone_map[key] = id
				logging.log(logger.DEBUG_ALL, "Keystone stat {} mapped to {}".format(id, key))
				keystone_ids.remove(id)

	logging.log(logger.DEBUG_ALL, keystone_map)

	assert len(keystone_ids) == 0

def is_whitelisted(group):
	for stat in whitelist:
		if stat in group['ids']:
			return True

	return False

def create_whitelist(data):
	global whitelist

	with open('stat_whitelist.json', 'r') as f:
		whitelist = json.load(f)

	# whitelist all support gem stats
	re_support = re.compile("Socketed Gems are Supported by Level", flags=re.IGNORECASE)
	support_gem_ids = []

	for translation_group in data:
		variations = translation_group['English']

		matched = False

		for variation in variations:
			if re_support.search(variation['string']):
				matched = True
				break

		if matched:
			for id in translation_group['ids']:
				support_gem_ids.append(id)
				logging.debug("Whitelisted stat '{}'".format(id))

	whitelist.extend(support_gem_ids)
	init_support_gem_stat_map(support_gem_ids)

	# whitelist all keystone stats
	re_keystone = re.compile("keystone_.+", flags=re.IGNORECASE)
	keystone_ids = []

	for translation_group in data:
		for id in translation_group['ids']:
			if re_keystone.match(id):
				keystone_ids.append(id)
				logging.debug("Whitelisted stat '{}'".format(id))

	whitelist.extend(keystone_ids)
	init_keystone_stat_map(keystone_ids)

def init():
	logging.debug("Initializing stat parsing...")

	global trans_data

	with open('data\\stat_translations.json', 'r') as f:
		logging.log(logger.DEBUG_ALL, "Loading stat_translations.json...")
		trans_data = json.load(f)

	for path in glob.glob("data\\stat_translations\\*.json"):
		logging.log(logger.DEBUG_ALL, "Loading {}...".format(path))

		with open(path, 'r') as f:
			trans_data.extend(json.load(f))

	# deduplicate
	logging.log(logger.DEBUG_ALL, "Deduplicating stat translation data...")
	trans_data = map(lambda e: json.loads(e), list(set(map(lambda e: json.dumps(e), trans_data))))
	logging.log(logger.DEBUG_ALL, "Finished deduplication.")

	create_whitelist(trans_data)
	logging.log(logger.DEBUG_ALL, "Created stat whitelist.")

	# apply stat whitelist
	trans_data = filter(is_whitelisted, trans_data)
	logging.log(logger.DEBUG_ALL, "Filtered translation data.")

	'''
	with open('whitelist_example.json', 'w') as f:
		json.dump(trans_data, f, sort_keys=True, indent=4)
	'''

	for translation_group in trans_data:
		ids = translation_group['ids']
		variations = translation_group['English']

		for variation in variations:
			variation['regex'] = make_regex(variation)
			logging.log(logger.DEBUG_ALL, 'Created regex for: "{}" ==>  "{}"'.format(variation['string'], variation['regex']))

	logging.debug("Stat parsing initialization complete.")


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
					match = re.search(pattern, trans_block, flags=re.IGNORECASE)
				except sre_constants.error as e:
					logging.error(pattern)
					raise e

				if match:
					if len(match.groups()) > 0:
						logging.log(logger.DEBUG_ALL, "Item text '{}' matches stat {} with values: {}".format(match.group(0).strip(), ids, match.groups()))
					else:
						logging.log(logger.DEBUG_ALL, "Item text '{}' matches stat {}".format(match.group(0).strip(), ids))

					# construct stat dict
					match_values = list(match.groups())
					stat_dict = {}

					for i in range(0, len(variation['format'])):
						stat_format = variation['format'][i]

						if stat_format == "ignore":
							stat_dict[ids[i]] = 1.0
						else:
							stat_dict[ids[i]] = float(match_values.pop(0))


					stat = stat_t(match.group(0).strip(), stat_dict, item=item, passive=passive)
					self.add(stat)

					#logging.info(pattern)

					trans_block = re.sub(pattern.strip(), "", trans_block, flags=re.IGNORECASE)

					#logging.info(trans_block)

		for match in re.finditer("[^\n]+", trans_block):
			logging.log(logger.DEBUG_ALL, "Non-matched modifier: '{}'".format(match.group()))

	def build_cache(self):
		self.dict_cache = {}

		for stat in self.stats:
			for id, value in stat.dict.items():
				if id not in self.dict_cache:
					self.dict_cache[id] = 0

				self.dict_cache[id] += value

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

		logging.log(logger.DEBUG_ALL, self.dict)

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

'''start = time.time()

test_mods = """100% increased Global Critical Strike Chance
75% increased Critical Strike Chance for Spells
40% reduced Soul Cost of Vaal Skills
Can have multiple Crafted Modifiers
78% increased Fire Damage
Adds 13 to 160 Lightning Damage to Spells
21% chance to Ignite"""

cs = combined_stats_t(test_mods, item=1)

logging.info(cs.dict())

logging.info(time.time()-start)'''