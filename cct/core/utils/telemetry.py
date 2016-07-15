import multiprocessing
import os
import psutil
import resource


def acquire_telemetry_info():
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    la = ', '.join([str(f) for f in os.getloadavg()])
    return {'processname': multiprocessing.current_process().name,
            'self': resource.getrusage(resource.RUSAGE_SELF),
            'children': resource.getrusage(resource.RUSAGE_CHILDREN),
            'inqueuelen': 0,
            'freephysmem': vm.available,
            'totalphysmem': vm.total,
            'freeswap': sm.free,
            'totalswap': sm.total,
            'loadavg': la,
            }
