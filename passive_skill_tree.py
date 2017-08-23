from data.passive_skills import opts 

nodes = {}

for node in opts['passiveSkillTreeData']['nodes']:
	nodes[node['id']] = node