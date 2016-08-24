import gc
import multiprocessing
import operator
import time


class Message(object):
    instances = 0

    def __init__(self, type, id, sender, **kwargs):
        self.__class__.instances += 1
        print('Creating a Message in {}'.format(multiprocessing.current_process()))
        if self.__class__.instances > 300:
            print('Alive message instances: ', self.__class__.instances, 'sender: ', sender)
            gc.collect()
        self._dict = {'type': type, 'id': id, 'sender': sender, 'timestamp': time.monotonic()}
        self._dict.update(kwargs)

    def __getitem__(self, item):
        return operator.getitem(self._dict, item)

    def __setitem__(self, key, value):
        return operator.setitem(self._dict, key, value)

    def __delitem__(self, key):
        return operator.delitem(self._dict, key)

    def __del__(self):
        print('Destroying a Message in {}'.format(multiprocessing.current_process()))
        self._dict = None
        self.__class__.instances -= 1


def worker(inqueue, outqueue):
    i = 0
    while True:
        msg = inqueue.get()
        print("Received: {}, {:d}".format(msg['type'], msg['id']))
        # del msg
        outqueue.put_nowait(Message('reply', i, 'backend', num=Message.instances))
        i += 1


inqueue = multiprocessing.Queue()
outqueue = multiprocessing.Queue()

process = multiprocessing.Process(None, worker, 'worker_process', (outqueue, inqueue))
process.daemon = True
process.start()
