# Python
import logging
import json
import copy

path = 'data/passive_skills.json'

logging.debug("Loading skill tree data from '{}'...".format(path))

with open(path) as f:
	data = json.load(f)

nodes = {}
nodes_by_name = {}

logging.debug("Parsing nodes from data...")

for key, value in list(data['nodes'].items()):
	try:
		nodes[int(key)] = copy.deepcopy(value)

		if value['name'] not in nodes_by_name:
			nodes_by_name[value['name']] = []

		nodes_by_name[value['name']].append(int(key))
	except ValueError as e:
		logging.debug("Skipped passive skill node key '{}'".format(key))

logging.debug("Initializing group data...")

groups = {}

for key, value in list(data['groups'].items()):
	groups[int(key)] = copy.deepcopy(value)

# We've copied everything we need, delete data now to free up memory
del data

logging.debug("Skill tree data parsing complete.")

def find_nodes_by_name(name):
	if name not in nodes_by_name:
		raise KeyError("Passive named '{}' does not exist".format(name))

	result_nodes = []

	for node_id in nodes_by_name[name]:
		result_nodes.append(nodes[node_id])

	return result_nodes