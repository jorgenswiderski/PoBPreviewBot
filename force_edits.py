from util import parse_time_str
from util import calc_deletion_check_time
import time

def main(time_str, dcl):
	sec = parse_time_str(time_str)
	
	dct = calc_deletion_check_time(None, comment_age=sec)
	
	threshold = time.time() + dct
	
	updated = []
	
	for entry in dcl:
		if int(entry['time']) < threshold:
			updated.append(entry['id'])
			entry['time'] = 0
			
	if len(updated) <= 10:
		print "Flagged comments for update: {}".format(updated)
	else:
		print "Flagged {} comments for update.".format( len(updated) )
	
	return dcl