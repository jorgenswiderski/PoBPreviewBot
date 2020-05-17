# Python
import logging
import json

# Self
from item import item_t
import stat_parsing
import logger
import copy
import passive_skill_tree

'''

 TODO:

 integrate with the rest of the program

'''

with open('data/cluster_jewels.json', 'r') as f:
	data = json.load(f)

class cluster_node_t(object):
	def __init__(self, subgraph):
		self.subgraph = subgraph
		self.jewel = subgraph.jewel

	@property
	def index(self):
		nodes = filter(lambda n: n[1] == self, self.subgraph.nodes.items())

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
		id += self.jewel.data['sizeIndex'] << 4

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

	@property
	def allocated(self):
		if self.subgraph.parent_socket is None:
			return False

		return self.get_id() in self.jewel.build.passives_by_id

	@property
	def stats(self):
		pass

class cluster_small_node_t(cluster_node_t):
	@property
	def stats(self):
		stat_str = '\n'.join(self.jewel.skill['stats'])

		return stat_parsing.combined_stats_t(stat_str, passive=self)

	@property
	def name(self):
		return self.jewel.skill['name']

class cluster_data_node_t(cluster_node_t):
	def __init__(self, subgraph, passive_id):
		self.passive_id = passive_id

		super(cluster_data_node_t, self).__init__(subgraph)

	@property
	def passive(self):
		return passive_skill_tree.nodes[self.passive_id]

	@property
	def stats(self):
		stat_str = '\n'.join(self.passive['stats'])

		return stat_parsing.combined_stats_t(stat_str, passive=self)

	@property
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

		for node in self.nodes.values():
			logging.log(logger.DEBUG_ALL, "Node {} ({}) allocation: {}".format(node.name, node.get_id(), node.allocated))

	@property
	def data(self):
		return self.jewel.data

	def __init_proxy_group__(self):
		node_id = int(self.parent_socket['expansionJewel']['proxy'])
		self.proxy_node = copy.deepcopy(passive_skill_tree.nodes[node_id])
		self.proxy_group = copy.deepcopy(passive_skill_tree.groups[self.proxy_node['group']])

	def __init_nodes__(self):
		logging.debug("Initializing nodes for socket {} ({} {} [{}])".format(self.parent_socket['skill'], self.jewel.name, self.jewel.base, self.jewel.id))

		# Special handling for keystones
		if self.jewel.keystone_id:
			self.nodes = { 0: cluster_data_node_t(self, self.jewel.keystone_id) }
			return

		indicies = {}
		node_count = self.jewel.node_count

		# First pass: sockets
		socket_count = self.jewel.socket_count

		if self.data['size'] == "Large" and socket_count == 1:
			# Large clusters always have the single jewel at index 6
			node_index = 6

			assert node_index not in indicies

			indicies[node_index] = cluster_socket_t(self, 1)
		else:
			assert socket_count <= len(self.data['socketIndicies']) and "Too many sockets!"
			get_jewels = [ 0, 2, 1 ]

			for i in range(0, socket_count):
				node_index = self.data['socketIndicies'][i]

				assert node_index not in indicies

				indicies[node_index] = cluster_socket_t(self, get_jewels[i])

		# Second pass: notables
		notable_count = self.jewel.notable_count
		notable_list = self.jewel.notable_list

		# assign notables to indices

		notable_index_list = []

		for node_index in self.data['notableIndicies']:
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

			if node_index not in indicies:
				notable_index_list.append(node_index)

		notable_index_list.sort()

		for base_node in notable_list:
			index = notable_list.index(base_node)

			# Get the index
			node_index = notable_index_list[index]

			assert node_index not in indicies

			indicies[node_index] = cluster_data_node_t(self, base_node[1])

		# Third pass: small fill
		small_count = node_count - socket_count - notable_count

		# Gather small indicies
		small_index_list = []

		for node_index in self.data['smallIndicies']:
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

			if node_index not in indicies:
				small_index_list.append(node_index)

		# Create the small nodes
		for index in range(0, small_count):
			# Get the index
			node_index = small_index_list[index]

			# TODO: inject the cluster jewel added mods here

			assert node_index not in indicies

			indicies[node_index] = cluster_small_node_t(self)

		logging.log(logger.DEBUG_ALL, "Indicies: {}".format(indicies))

		assert indicies[0] and "No entrance to subgraph"

		self.nodes = indicies

class cluster_jewel_t(item_t):
	def __init__(self, build, item_xml):
		super(cluster_jewel_t, self).__init__(build, item_xml)
		
		self.__init_skill__()
		self.__init_keystone__()
		self.__init_notables__()
		self.__init_subgraphs__()
	
	@property
	def node_count(self):
		if 'local_jewel_expansion_passive_node_count' in self.stats.dict():
			return int(self.stats.dict()['local_jewel_expansion_passive_node_count'])
		else:
			return self.socket_count + self.notable_count + self.nothingness_count

	@property
	def socket_count(self):
		if 'local_jewel_expansion_jewels_count' in self.stats.dict():
			return int(self.stats.dict()['local_jewel_expansion_jewels_count'])
		else:
			return 0

	@property
	def notable_count(self):
		return len(self.notable_stats)

	@property
	def nothingness_count(self):
		if 'local_unique_jewel_grants_x_empty_passives' in self.stats.dict():
			return int(self.stats.dict()['local_unique_jewel_grants_x_empty_passives'])
		else:
			return 0
	
	@property
	def data(self):
		return data['jewels'][self.base]

	'''
	@property
	def stats(self):
		stats = stat_parsing.combined_stats_t('', item=self)

		for node in self.nodes:
			if node.allocated:
				stats += node.stats

		return stats
	'''

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

		for id, values in self.data['skills'].items():
			for row in rows:
				if values['enchant'][0].lower() in row.lower():
					self.skill = copy.deepcopy(values)
					break

			if self.skill:
				break

		if self.skill:
			logging.debug("{} {} [{}] skill is {} ({})".format(self.name, self.base, self.id, self.skill['name'], self.skill['tag']))
		else:
			log_level = logging.DEBUG if self.rarity == "UNIQUE" else logging.WARNING
			logging.log(log_level, "{} {} [{}] has no skill".format(self.name, self.base, self.id))

	def __init_keystone__(self):
		for stat in self.stats.dict():
			if stat in stat_parsing.cluster_keystone_map:
				self.keystone_id = stat_parsing.cluster_keystone_map[stat]
				#self.keystone = passive_skill_tree.nodes[self.keystone_id]
				return

		self.keystone_id = None
		#self.keystone = None

	def __init_notables__(self):
		self.notable_stats = []

		for stat in self.stats.dict():
			if stat in stat_parsing.cluster_notable_map:
				self.notable_stats.append(stat)

		# make notable list from stats
		self.notable_list = []

		for stat in self.notable_stats:
			self.notable_list.append(stat_parsing.cluster_notable_map[stat])

		self.notable_list.sort(key=lambda n: data['notableSortOrder'][n[0]])

		logging.log(logger.DEBUG_ALL, "Sorted notable order: {}".format(self.notable_list))

	def __init_subgraphs__(self):
		self.subgraphs = []

		sockets = self.build.xml.find('Tree').find('Spec').find('Sockets')

		for socket in sockets.findall('Socket'):
			if int(socket.attrib['itemId']) == self.id:
				node_id = int(socket.attrib['nodeId'])

				# only generate a subgraph for that socket if the socket is allocated
				if node_id in self.build.passives_by_id:
					self.subgraphs.append(subgraph_t(self, node_id))
