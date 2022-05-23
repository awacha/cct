import os
import re

def check(filename: str):
    # first load it and find all lines with .connect()
    with open(filename, 'rt') as f:
        slots = set()
        signals = set()
        for iline, line in enumerate(f):
            if m := re.match(r'.*\.connect\((?P<slot>.*)\)\s*$', line):
#                print(filename, m['slot'].strip())
                slots.add(m['slot'].strip())
            elif m := re.match(r'\s*(?P<signalname>[a-zA-Z0-9]+)\s*=\s*Signal\(', line):
                signals.add(m['signalname'])
    if not slots:
        return
    slotmethods = {s for s in slots if s.startswith('self.')}
    slottedmethods = set()
    notslottedmethods = set()
    otherslots = {s for s in slots if s not in slotmethods}
    signalslots = {s for s in slots if s[5:] in signals}
    with open(filename, 'rt') as f:
        prevline = None
        for iline, line in enumerate(f):
            if m := re.match(r'^\s+def\s+(?P<methodname>[a-zA-Z_0-9]+)\(.*$', line):
                # we have a function
                slotmethod = [s for s in slotmethods if s[5:] == m['methodname']]
                if slotmethod:
                    if prevline.strip().startswith('@Slot('):
                        slottedmethods.add(slotmethod[0])
                    else:
                        notslottedmethods.add(slotmethod[0])
            prevline = line
    membermethods = {s for s in  slotmethods if s.count('.') > 1}
    unknownmethods = {s for s in slotmethods if s not in slottedmethods and s not in notslottedmethods and s not in signalslots and s not in membermethods}
    if any([notslottedmethods, otherslots, unknownmethods]):
        print(filename)
        if notslottedmethods:
            print('   Methods need decorating:\n' + "\n".join(["      " + m for m in notslottedmethods]))
#        if slottedmethods:
#            print(f'   Methods already decorated: {slottedmethods}')
#        if signalslots:
#            print(f'   Signal slots: {signalslots}')
        if otherslots:
            print(f'   Other slots (not methods or signals): {otherslots}')
#        if membermethods:
#            print(f'   Member methods: {membermethods}')
        if unknownmethods:
            print(f'   Unknown methods (probably defined in a superclass): {unknownmethods}')


for folder, dirs, files in os.walk('cct', topdown=True):
    for filename in sorted(files):
        filename = os.path.join(folder, filename)
        if not filename.endswith('.py'):
            continue
        check(filename)