import multiprocessing
import operator
import time


class Message(object):
    instances = 0

    def __new__(cls, *args, **kwargs):
        cls.instances += 1
        print('Creating a Message in {}'.format(multiprocessing.current_process()))
        obj = object.__new__(cls)
        print('Created.')
        return obj

    def __init__(self, type, id, sender, **kwargs):
        print('Initializing.')
        self.__class__.instances += 1
        self._dict = {'type': type, 'id': id, 'sender': sender, 'timestamp': time.monotonic()}
        self._dict.update(kwargs)
        self._destroyed = False
        print('Initialized.')

    def __getitem__(self, item):
        return operator.getitem(self._dict, item)

    def __setitem__(self, key, value):
        return operator.setitem(self._dict, key, value)

    def __delitem__(self, key):
        return operator.delitem(self._dict, key)

    def __del__(self):
        if self._destroyed:
            print('Attempt to destroy Message more than once!')
            return
        print('Destroying a Message in {}'.format(multiprocessing.current_process()))
        self._destroyed = True
        self._dict = None
        self.__class__.instances -= 1
        print('Destroyed')


def worker(inqueue, outqueue):
    i = 0
    while True:
        msg = inqueue.get()
        print("Received: {}, {}".format(msg['type'], msg['id']))
        if msg['id'] == 'Exit':
            break
        del msg
        outqueue.put_nowait(Message('reply', i, 'backend', num=Message.instances))
        i += 1


inqueue = multiprocessing.Queue()
outqueue = multiprocessing.Queue()

process = multiprocessing.Process(None, worker, 'worker_process', (outqueue, inqueue))
process.daemon = True
process.start()
