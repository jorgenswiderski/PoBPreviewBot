# Python
import logging
import json

path = 'data\\passive_skills.json'

logging.debug("Loading skill tree data from '{}'...".format(path))

with open(path) as f:
	data = json.load(f)

nodes = {}

logging.debug("Parsing nodes from data...")

for key, value in data['nodes'].iteritems():
	try:
		nodes[int(key)] = value
	except ValueError as e:
		logging.debug("Skipped passive skill node key '{}'".format(key))

logging.debug("Skill tree data parsing complete.")