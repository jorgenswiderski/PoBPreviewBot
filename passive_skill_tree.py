from data.passive_skills import passiveSkillTreeData as data 

nodes = {}

for node in data['nodes']:
	nodes[node['id']] = node