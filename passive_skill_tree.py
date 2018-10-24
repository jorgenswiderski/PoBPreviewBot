from data.passive_skills import passiveSkillTreeData as data 

nodes = {}

for key, value in data['nodes'].iteritems():
	nodes[str(key)] = value