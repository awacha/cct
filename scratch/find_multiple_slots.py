import os
import re

for directory, dirs, files in os.walk('../cct'):
    for filename in files:
        if not filename.endswith('.py'):
            continue
        fullfile = os.path.join(directory, filename)
#        print(fullfile)
        with open(fullfile, 'rt') as f:
            num_slot_lines = 0
            last_slot_name = None
            for iline, line in enumerate(f):
                if m := re.match('\\s*@Slot\\(.*name\\s*=\\s*(?P<delim>[\'\"])(?P<name>.+)(?P=delim)\\s*\\)', line):
                    num_slot_lines += 1
                    if (last_slot_name is not None) and (last_slot_name != m['name']):
                        print(f'Redefining slot name from {last_slot_name} to {m["name"]} in file {fullfile}, '
                              f'line {iline+1}')
                    last_slot_name = m['name']

                elif m := re.match('\\s*def\\s+(?P<name>.+)\\(\\s*self', line):
                    if num_slot_lines > 1:
                        print(f'Function {m["name"]} in file {fullfile} on line {iline+1} has {num_slot_lines} '
                              f'slot decorators')
                    if (last_slot_name is not None) and (m["name"] != last_slot_name):
                        print(f'Name of function {m["name"]} differs from the last slot name {last_slot_name} '
                              f'in file {fullfile} on line {iline+1}')
                    num_slot_lines = 0
                elif m := re.match('\\s*@Slot\\(', line):
                    num_slot_lines += 1
