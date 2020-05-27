import inspect
import logging
import time
import statistics as stats

cumulative_data = {}

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

        try:
            is_method = inspect.getfullargspec(f)[0][0] == 'self'
        except IndexError:
            is_method = False

        key = None

        if is_method:
            key = "{}.{}".format(args[0].__class__.__name__, f.__name__)
        else:
            key = f.__name__

        if key not in cumulative_data:
        	cumulative_data[key] = []

        cumulative_data[key].append(end-start)

        return result

    return f_timer

def log_digest():
    if cumulative_data:
        logging.info("       \tSUM\tMEAN\tMEDIAN\tMIN\tMAX\tCOUNT\tDESC")
        logging.info("=========================================================================================")

    for entry in sorted(list(cumulative_data.items()), key=lambda i: i[0]):
        key = entry[0]
        vals = entry[1]
        #logging.info("Total time spent on '{}': {:.3f}s".format(method_names[key], vals))
        logging.info("Profile\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{:.3f}s\t{}\t{}".format(sum(vals), stats.mean(vals), stats.median(vals), min(vals), max(vals), len(vals), key))

class ChunkProfiler(object):
    def __init__(self, desc):
        self.desc = desc
        self.key = "chunk-{}".format(self.desc)

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, type, value, traceback):
        duration = time.time() - self.start

        if self.key not in cumulative_data:
            cumulative_data[self.key] = []

        cumulative_data[self.key].append(duration)
