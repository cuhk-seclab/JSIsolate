#!/usr/bin/python

import subprocess, sys

def get_RSS(pid):
    fn = "/proc/%d/smaps" % pid
    try:
        fstr = open(fn).read()

        mem = 0
        for line in fstr.split("\n"):
            if line.startswith("Private_Dirty:"):
                mem_str = line.split(":", 1)[1].strip()
                mem += int(mem_str.split()[0])
    except Exception:
        mem = -1
    return mem

def get_pids_by_name(name):
    return list(map(int,subprocess.check_output(["pidof",name]).split()))
    
def get_mem_by_name(name):
    pids = get_pids_by_name(name)
    return get_mem_by_pids(pids)

def get_mem_by_pids(pids):
    total_mem = 0
    for pid in pids:
        mem = get_RSS(pid)
        total_mem += mem
    return total_mem

if __name__ == "__main__":
    if(len(sys.argv) < 2):
        print('ERROR MEM')
    else:
        pids = list()
        pids.append(int(sys.argv[1]))
        print(get_mem_by_pids(pids))
