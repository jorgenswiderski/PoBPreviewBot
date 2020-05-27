# Python
import logging
import json
from functools import cached_property

# Self
from item import item_t
import stat_parsing
import logger
import copy
import passive_skill_tree

# TODO: Convert to cached properties

# load in a function to aid garbage collection
def init():
	with open('data/cluster_jewels.json', 'r') as f:
		raw_data = json.load(f)

		global data
		data = {}

		# Initialized hardcoded size indices
		# This value is not from the game data but is present in PoB, so we supplement here
		size_indices = {
			'Large': 2,
			'Medium': 1,
			'Small': 0
		}

		for key, value in list(raw_data.items()):
			value['size_index'] = size_indices[value['size']]
			data[value['name']] = value

			for skill_data in value['passive_skills']:
				# Add enchant value
				skill_data['enchant'] = []

				for stat_id, value in list(skill_data['stats'].items()):
					stat = stat_parsing.stat_t(None, {stat_id: value})

					stat_str = stat.string

					# blargh, phys damage stat translates to "global phys damage" even though thats now how it works ingame
					# spaghet
					if stat_id == "physical_damage_+%":
						stat_str = "{0}% increased Physical Damage".format(value)
					elif stat_id == "critical_strike_chance_+%":
						stat_str = "{0}% increased Critical Strike Chance".format(value)

					skill_data['enchant'].append("Added Small Passive Skills grant: {}".format(stat_str))
					del stat

	with open('data/cluster_jewel_notables.json', 'r') as f:
		notable_data = json.load(f)

		# Create these dicts
		global notable_sort_order
		notable_sort_order = {}
		global cluster_notable_map
		cluster_notable_map = {}
		global cluster_keystone_map
		cluster_keystone_map = {}

		for notable in notable_data:
			# Create sort order entry
			notable_sort_order[notable['name']] = notable_data.index(notable)

			# Create notable / keystone map entry
			try:
				matching_nodes = passive_skill_tree.find_nodes_by_name(notable['name'])
			except KeyError:
				logging.warning("No passive found for {} ({})".format(notable['name'], notable['jewel_stat']))
				continue

			assert len(matching_nodes) == 1

			if 'isKeystone' in matching_nodes[0] and matching_nodes[0]['isKeystone']:
				cluster_keystone_map[notable['jewel_stat']] = (notable['name'], matching_nodes[0]['skill'])
			elif 'isNotable' in matching_nodes[0] and matching_nodes[0]['isNotable']:
				cluster_notable_map[notable['jewel_stat']] = (notable['name'], matching_nodes[0]['skill'])
			else:
				raise RuntimeError("Cluster jewel notable found passive that is neither a notable or a keystone")

			#logging.info("'{}' mapped to passive {} ({})".format(notable['jewel_stat'], notable['name'], matching_nodes[0]['skill']))

	# define bases for constructor selection in item.py
	global bases
	bases = [x['name'] for x in data.values()]

class cluster_node_t(object):
	def __init__(self, subgraph):
		self.subgraph = subgraph
		self.jewel = subgraph.jewel

	@cached_property
	def index(self):
		nodes = [n for n in list(self.subgraph.nodes.items()) if n[1] == self]

		assert len(nodes) == 1

		#logging.info("{} node index is {}".format(self, nodes[0][0]))

		return nodes[0][0]

	'''
	Generate an ID for the node the same way PoB does. This is an unofficial method of ID generation.

	Reference:
	https://github.com/PathOfBuildingCommunity/PathOfBuilding/blob/acf47d219f9d463a3286d97129ee4f6448f62444/Classes/PassiveSpec.lua#L637
	'''
	def get_id(self):
		if self.subgraph.parent_socket is None:
			return None

		'''
		Make id for this subgraph (and nodes)
		0-3: Node index (0-11)
		4-5: Group size (0-2)
		6-8: Large index (0-5)
		9-10: Medium index (0-2)
		11-15: Unused
		16: 1 (signal bit, to prevent conflict with node hashes)
		'''
		id = 65536

		# Step 1: Node index
		id += self.index

		# Step 2: Group size
		id += self.jewel.data['size_index'] << 4

		# Step 3: Large index
		node = self.subgraph.parent_socket

		# Climb the node tree until we find the parent socket / grandparent socket etc that is large
		while node['expansionJewel']['size'] < 2:
			parent_id = int(node['expansionJewel']['parent'])
			node = passive_skill_tree.nodes[parent_id]

		assert node['expansionJewel']['size'] == 2

		# Add its index
		id += node['expansionJewel']['index'] << 6

		# Step 4: Medium index
		# If the parent socket is medium or smaller
		if self.subgraph.parent_socket['expansionJewel']['size'] <= 1:
			node = self.subgraph.parent_socket

			# Climb the node tree until we find the parent socket / grandparent socket etc that is medium
			while node['expansionJewel']['size'] < 1:
				parent_id = int(node['expansionJewel']['parent'])
				node = passive_skill_tree.nodes[parent_id]

			assert node['expansionJewel']['size'] == 1

			# Add its index
			id += node['expansionJewel']['index'] << 9

		'''
		Example bitmask
		65856   320     00101000000

		node index: 0   -------0000
		group size: 0   -----00----
		large index: 5	--101------
		medium index: 0 00---------
		'''

		return id

	@cached_property
	def allocated(self):
		if self.subgraph.parent_socket is None:
			return False

		return self.get_id() in self.jewel.build.passives_by_id

	@cached_property
	def stats(self):
		pass

	@cached_property
	def name(self):
		pass

class cluster_small_node_t(cluster_node_t):
	@cached_property
	def stats(self):
		return stat_parsing.combined_stats_t(None, stats_dict=self.jewel.skill['stats'], passive=self)

	@cached_property
	def name(self):
		if self.jewel.skill:
			self.jewel.skill['name']
		else:
			raise RuntimeError("{} has no skill".format(self.jewel))

class cluster_data_node_t(cluster_node_t):
	def __init__(self, subgraph, passive_id):
		self.passive_id = passive_id

		super(cluster_data_node_t, self).__init__(subgraph)

	@cached_property
	def passive(self):
		return passive_skill_tree.nodes[self.passive_id]

	@cached_property
	def stats(self):
		stat_str = '\n'.join(self.passive['stats'])

		return stat_parsing.combined_stats_t(stat_str, passive=self)

	@cached_property
	def name(self):
		return self.passive['name']

# this is basically a helper-constructor that automatically finds the right passive id for the socket
class cluster_socket_t(cluster_data_node_t):
	def __init__(self, subgraph, socket_index):
		passive_id = self.find_socket(subgraph.proxy_group, socket_index)

		super(cluster_socket_t, self).__init__(subgraph, passive_id)

	@classmethod
	def find_socket(cls, group, socket_index):
		# Find the given socket index in the group
		for node_id in group['nodes']:
			node = passive_skill_tree.nodes[int(node_id)]

			if 'expansionJewel' in node and node['expansionJewel']['index'] == socket_index:
				return int(node_id)

	def get_id(self):
		return self.passive_id

class subgraph_t():
	def __init__(self, jewel, socket_id):
		self.jewel = jewel
		self.parent_socket = copy.deepcopy(passive_skill_tree.nodes[socket_id])
		self.skill = jewel.skill

		self.__init_proxy_group__()
		self.__init_nodes__()

		#for node in self.nodes.values():
		#	logging.info("Cluster jewel passive node {} ({}) allocation is: {}".format(node.name, node.get_id(), node.allocated))

	@cached_property
	def data(self):
		return self.jewel.data

	def __init_proxy_group__(self):
		node_id = int(self.parent_socket['expansionJewel']['proxy'])
		self.proxy_node = copy.deepcopy(passive_skill_tree.nodes[node_id])
		self.proxy_group = copy.deepcopy(passive_skill_tree.groups[self.proxy_node['group']])

	def __init_nodes__(self):
		#logging.info("Initializing nodes for socket {} ({})".format(self.parent_socket['skill'], self.jewel))

		# Special handling for keystones
		if self.jewel.keystone_id:
			self.nodes = { 0: cluster_data_node_t(self, self.jewel.keystone_id) }
			return

		indices = {}
		node_count = self.jewel.node_count

		# First pass: sockets
		socket_count = self.jewel.socket_count

		if self.data['size'] == "Large" and socket_count == 1:
			# Large clusters always have the single jewel at index 6
			node_index = 6

			assert node_index not in indices

			indices[node_index] = cluster_socket_t(self, 1)
		else:
			assert socket_count <= len(self.data['socket_indices']) and "Too many sockets!"
			get_jewels = [ 0, 2, 1 ]

			for i in range(0, socket_count):
				node_index = self.data['socket_indices'][i]

				assert node_index not in indices

				indices[node_index] = cluster_socket_t(self, get_jewels[i])

		# Second pass: notables
		notable_count = self.jewel.notable_count
		notable_list = self.jewel.notable_list

		# assign notables to indices

		notable_index_list = []

		for node_index in self.data['notable_indices']:
			if len(notable_index_list) == notable_count:
				break

			if self.data['size'] == "Medium":
				if socket_count == 0 and notable_count == 2:
					# Special rule for two notables in a Medium cluster
					if node_index == 6:
						node_index = 4
					elif node_index == 10:
						node_index = 8
				elif node_count == 4:
					# Special rule for notables in a 4-node Medium cluster
					if node_index == 10:
						node_index = 9
					elif node_index == 2:
						node_index = 3

			if node_index not in indices:
				notable_index_list.append(node_index)

		notable_index_list.sort()

		for base_node in notable_list:
			index = notable_list.index(base_node)

			if index >= len(notable_index_list):
				# Jewel has more notables than is possible
				# Mirror PoB's approach and just silently ignore excess notables
				break

			# Get the index
			node_index = notable_index_list[index]

			assert node_index not in indices

			indices[node_index] = cluster_data_node_t(self, base_node[1])

		# Third pass: small fill
		small_count = node_count - socket_count - notable_count

		# Gather small indices
		small_index_list = []

		for node_index in self.data['small_indices']:
			if len(small_index_list) == small_count:
				break

			if self.data['size'] == "Medium":
				# Special rules for small nodes in Medium clusters
				if node_count == 5 and node_index == 4:
					node_index = 3
				elif node_count == 4:
					if node_index == 8:
						node_index = 9
					elif node_index == 4:
						node_index = 3

			if node_index not in indices:
				small_index_list.append(node_index)

		# Create the small nodes
		for index in range(0, small_count):
			# Get the index
			node_index = small_index_list[index]

			# TODO: inject the cluster jewel added mods here

			assert node_index not in indices

			indices[node_index] = cluster_small_node_t(self)

		#logging.info("indices: {}".format(indices))

		assert indices[0] and "No entrance to subgraph"

		self.nodes = indices

class cluster_jewel_t(item_t):
	def __init__(self, build, item_xml):
		super(cluster_jewel_t, self).__init__(build, item_xml)
		
		self.__init_notables__()
		self.__init_skill__()
		self.__init_keystone__()
		self.__init_subgraphs__()
		self.__update_build_passives__()

	def __str__(self):
		return "{} {} [{}]".format(self.name, self.base, self.id)
	
	@cached_property
	def node_count(self):
		if 'local_jewel_expansion_passive_node_count' in self.stats.dict():
			return int(self.stats.dict()['local_jewel_expansion_passive_node_count'])
		else:
			return self.socket_count + self.notable_count + self.nothingness_count

	@cached_property
	def socket_count(self):
		if 'local_jewel_expansion_jewels_count_override' in self.stats.dict():
			return int(self.stats.dict()['local_jewel_expansion_jewels_count_override'])
		if 'local_jewel_expansion_jewels_count' in self.stats.dict():
			return int(self.stats.dict()['local_jewel_expansion_jewels_count'])
		else:
			return 0

	@cached_property
	def notable_count(self):
		return len(self.notable_stats)

	@cached_property
	def nothingness_count(self):
		if 'local_unique_jewel_grants_x_empty_passives' in self.stats.dict():
			# Voices
			return int(self.stats.dict()['local_unique_jewel_grants_x_empty_passives'])
		elif 'local_affliction_jewel_display_small_nodes_grant_nothing' in self.stats.dict():
			# Megalomaniac

			# Make sure the number of points is specified, or this won't work (stack overflow)
			assert 'local_jewel_expansion_passive_node_count' in self.stats.dict()

			return self.node_count - self.socket_count - self.notable_count
		else:
			return 0
	
	@cached_property
	def data(self):
		return data[self.base]

	def __init_skill__(self):
		if self.nothingness_count > 0:
			self.skill = {
				"name": "Nothingness",
				"tag": None,
				"stats": []
			}
			return


		rows = self.xml.text.split('\n')
		self.skill = None

		for skill_data in self.data['passive_skills']:
			for row in rows:
				if skill_data['enchant'][0].lower() in row.lower():
					self.skill = copy.deepcopy(skill_data)
					break

			if self.skill:
				break

		if self.skill:
			logging.debug("{} skill is {} ({})".format(self, self.skill['name'], self.skill['id']))
		else:
			log_level = logging.DEBUG if self.rarity == "UNIQUE" else logging.WARNING
			logging.log(log_level, "{} has no skill".format(self))

	def __init_keystone__(self):
		for stat in self.stats.dict():
			if stat in cluster_keystone_map:
				self.keystone_id = cluster_keystone_map[stat][1]
				#self.keystone = passive_skill_tree.nodes[self.keystone_id]
				return

		self.keystone_id = None
		#self.keystone = None

	def __init_notables__(self):
		self.notable_stats = []

		for stat in self.stats.dict():
			if stat in cluster_notable_map:
				self.notable_stats.append(stat)

		# make notable list from stats
		self.notable_list = []

		for stat in self.notable_stats:
			self.notable_list.append(cluster_notable_map[stat])

		self.notable_list.sort(key=lambda n: notable_sort_order[n[0]])

		logging.log(logger.DEBUG_ALL, "Sorted notable order: {}".format(self.notable_list))

	def __init_subgraphs__(self):
		self.subgraphs = []

		for socket in self.build.xml.findall('Tree/Spec/Sockets/Socket'):
			if int(socket.attrib['itemId']) == self.id:
				node_id = int(socket.attrib['nodeId'])

				# only generate a subgraph for that socket if the socket is allocated
				if node_id in self.build.passives_by_id:
					self.subgraphs.append(subgraph_t(self, node_id))

	def __update_build_passives__(self):
		for subgraph in self.subgraphs:
			for node in list(subgraph.nodes.values()):
				if node.allocated:
					self.build.passives_by_name[node.name] = node.get_id()
