import inspect
import logging
import time

cumulative_data = {}
method_names = {}

def mean(l):
    return sum(l) / len(l)

def median(l):
    sl = sorted(l)
    n = len(sl)

    if n % 2 == 0:
        return (sl[n//2]+sl[n//2-1])/2
    else:
        return sl[n//2]


def profile(f):
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        logging.info("{}.{} call took {}s.".format(f.__module__, f.__name__, end-start))

        return result

    return f_timer

def profile_cumulative(f):
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()

        if f.__name__ not in cumulative_data:
	        try:
	        	is_method = inspect.getfullargspec(f)[0][0] == 'self'
	        except IndexError:
	        	is_method = False

	        name = ""

	        if is_method:
	        	name = "{}.{}".format(args[0].__class__.__name__, f.__name__)
	        else:
	        	name = f.__name__

        	cumulative_data[f.__name__] = []
        	method_names[f.__name__] = name

        cumulative_data[f.__name__].append(end-start)

        return result

    return f_timer

def log_digest():
    if cumulative_data:
        logging.info("       \tSUM\tMEAN\tMEDIAN\tMIN\tMAX\tCOUNT\tDESC")
        logging.info("=========================================================================================")

    for entry in cumulative_data.items():
        key = entry[0]
        vals = entry[1]
        #logging.info("Total time spent on '{}': {:.3f}s".format(method_names[key], vals))
        logging.info("Profile\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{}\t{}".format(sum(vals), mean(vals), median(vals), min(vals), max(vals), len(vals), method_names[key]))

class ChunkProfiler(object):
    def __init__(self, desc):
        self.desc = desc

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, type, value, traceback):
        duration = time.time() - self.start

        if self.desc not in cumulative_data:
            cumulative_data[self.desc] = []
            method_names[self.desc] = "chunk-{}".format(self.desc)

        cumulative_data[self.desc].append(duration)
