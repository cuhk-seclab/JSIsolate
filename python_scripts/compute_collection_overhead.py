import json, os, sys, traceback, getopt

def measure(user_dir, task_id, start, end):
    global type2rank2time, type2rank2mem


    current_pid = os.getpid()
    current_dir = os.getcwd()

    input_dir = user_dir + '_logs'
    files = os.listdir(input_dir)
    time_files = [f for f in files if f.endswith('.time')]
    iso_time_files = [f for f in files if f.endswith('.time_collect')]
    mem_files = [f for f in files if f.endswith('.mem')]
    iso_mem_files = [f for f in files if f.endswith('.mem_collect')]


    for f in time_files: 
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'r') as input_f:
            for line in input_f:
                time = json.loads(line.split('\n')[0])
                break
            rank = int(f.split('.')[0])
            if rank < start or rank > end:
                continue
            type2rank2time['clean'][rank] = time
            

    for f in iso_time_files:
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'r') as input_f:
            for line in input_f:
                time = json.loads(line.split('\n')[0])
                break
            rank = int(f.split('.')[0])
            if rank < start or rank > end:
                continue
            type2rank2time['isolate'][rank] = time

    clean_valid_mem_ranks = set()
    for f in mem_files: 
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'rb') as input_f:
            for line in input_f:
                line = str(line, 'utf-8')
                if line != '-1':
                    line = line[2:-1]
                mem = int(line.split('\\n')[0])
                break
            rank = int(f.split('.')[0])
            if rank < start or rank > end: 
                continue
            if mem != -1:
                clean_valid_mem_ranks.add(rank)
                type2rank2mem['clean'][rank] = mem

    iso_valid_mem_ranks = set()
    for f in iso_mem_files:
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'rb') as input_f:
            for line in input_f:
                line = str(line, 'utf-8')
                if line != '-1':
                    line = line[2:-1]
                mem = int(line.split('\\n')[0])
                break
            rank = int(f.split('.')[0])
            if rank < start or rank > end: 
                continue
            if rank not in clean_valid_mem_ranks:
                continue
            if mem != -1:
                iso_valid_mem_ranks.add(rank)
                type2rank2mem['isolate'][rank] = mem


def main(argv):
    global num_instances, type2rank2time, type2rank2mem

    parent_pid = os.getpid()
    try:
        opts, args = getopt.getopt(argv, 'hu:d:i:n:p:s:e:t:o:', ['help', 'user_dir=', 'exp_dir=', 'num=', 'process=', 'start=', 'end=', 'type=', 'output_dir='])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

        
    user_dir = None
    num_instances = 512
    maximum_process_num = 8 # Change to 1 for debugging purpose
    start = 0
    end = None
    exp_dir = "exps"
    extract = False
    clean = False
    send = False
    input_type = 'url2index'
    for opt, arg in opts:
        if opt in ('-u', '--user_dir'):
            user_dir = arg
        elif opt in ('-d', '--dir'):
            exp_dir = arg
        elif opt in ('-n', '--num'):
            num_instances = int(arg)
        elif opt in ('-p', '--process'):
            maximum_process_num = int(arg)
        elif opt in ('-s', '--start'):
            start = int(arg)
        elif opt in ('-e', '--end'):
            end = int(arg)
        elif opt in ('-t', '--type'):
            input_type = arg
        elif opt in ('-o', '--output_dir'):
            output_dir = arg
        elif opt in ('-h', '--help'):
            usage()
            sys.exit(0)


    
    type2rank2time = {'isolate':dict(), 'clean': dict()}
    type2rank2mem = {'isolate':dict(), 'clean': dict()}
    input_file = 'top-1m.csv'
    rank2domain = dict()
    with open(input_file, 'r') as input_f:
        for line in input_f:
            split_list = line.split('\n')[0].split(',')
            if int(split_list[0]) > 1000:
                break
            rank2domain[split_list[0]] = split_list[1]

    raw_data_dir = exp_dir

    try:
        os.chdir(exp_dir)
    except OSError as e:
        sys.exit(1)


    tasks = [i for i in range(num_instances-1, -1, -1)]
    for task in tasks:
        user_dir_group = '%s_%d' %(user_dir, task)
        try:
            measure(user_dir_group, task, start, end)
        except OSError as e:
            continue
    
    output_file = 'collect-type2rank2time.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(type2rank2time))
        
    output_file = 'collect-type2rank2mem.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(type2rank2mem))


    clean_times = {'navi-dom': list(), 'navi-load': list(), 'response-dom': list(), 'response-load': list(),  'pure': list()} 
    isolate_times = {'navi-dom': list(), 'navi-load': list(), 'response-dom': list(), 'response-load': list(), 'pure': list()} 
    clean_mems = list()
    isolate_mems = list()
    type2rank2overhead = {'time': dict(), 'memory': dict()}
    clean_time_ranks = list(type2rank2time['clean'].keys())
    isolate_time_ranks = list(type2rank2time['isolate'].keys())

    for type_, rank2time in list(type2rank2time.items()):
        for rank, time in list(rank2time.items()):
            if rank not in clean_time_ranks or rank not in isolate_time_ranks:
                continue
            if type_ == 'clean':
                for key, value in list(time.items()):
                    clean_times[key].append(value)
            else:
                for key, value in list(time.items()):
                    isolate_times[key].append(value)

 
    clean_mem_ranks = list(type2rank2mem['clean'].keys())
    isolate_mem_ranks = list(type2rank2mem['isolate'].keys())
    mem_ranks = set()

    for type_, rank2mem in list(type2rank2mem.items()):
        for rank, mem in list(rank2mem.items()):
            if rank not in clean_mem_ranks or rank not in isolate_mem_ranks:
                continue

            mem_ranks.add(rank)
            if type_ == 'clean':
                clean_mems.append(mem)
            else:
                isolate_mems.append(mem)

    for rank in clean_time_ranks:
        if rank not in isolate_time_ranks:
            continue
        if rank not in type2rank2overhead['time']:
            type2rank2overhead['time'][rank] = {'navi-dom': 0, 'navi-load': 0, 'response-dom': 0, 'response-load': 0, 'pure': 0}

        for key in ['navi-dom', 'navi-load', 'response-dom', 'response-load', 'pure']:
            overhead = type2rank2time['isolate'][rank][key] / (type2rank2time['clean'][rank][key] * 1.0)
            type2rank2overhead['time'][rank][key] = overhead

    for rank in clean_mem_ranks:
        if rank not in isolate_mem_ranks:
            continue
        if rank not in type2rank2overhead['memory']:
            type2rank2overhead['memory'][rank] = type2rank2mem['isolate'][rank] / (type2rank2mem['clean'][rank] * 1.0)
           

    output_file = 'type2rank2overhead.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(type2rank2overhead))

    print('\n\n\nAverage page loading time')
    for key in list(clean_times.keys()):
        cur_clean_times = clean_times[key]
        cur_collect_times = isolate_times[key]
        if key not in ['navi-dom']: # the page loading time shall be measured from navigationStart to domComplete
            continue
        print(('\t%s'%(key)))
        print(('#Websites: %d'%(len(cur_clean_times)))) 
        cur_clean_times_ = cur_clean_times
        cur_collect_times_ = cur_collect_times

        clean_mean_time = sum(cur_clean_times_) / (max(len(cur_clean_times_), 1) * 1.0)
        isolate_mean_time = sum(cur_collect_times_) / (max(len(cur_collect_times_), 1) * 1.0)
        overhead_mean_time = isolate_mean_time / (clean_mean_time * 1.0)
        overhead_times = [cur_collect_times_[i]/(cur_clean_times_[i]*1.0) for i in range(0, len(cur_clean_times_))]

        print(('\tclean: %.3f\tisolate: %.3f\toverhead: %.3f'%(clean_mean_time, isolate_mean_time, overhead_mean_time)))
        print(('\tmax overhead: %.3f'%(max(overhead_times))))
        print(('\tmin overhead: %.3f'%(min(overhead_times))))
        overhead_len = len(overhead_times)
        overhead_times = sorted(overhead_times)
        if overhead_len%2 == 0:
            target_index = overhead_len//2-1
            median = (overhead_times[target_index] + overhead_times[target_index+1]) / 2.0
        else:
            target_index = overhead_len//2
            median = overhead_times[target_index]
        print(('\tmedian overhead: %.3f'%(median)))
        print('\n')


    clean_mean_mem = sum(clean_mems) / (max(len(clean_mems), 1) * 1.0)
    isolate_mean_mem = sum(isolate_mems) / (max(len(isolate_mems), 1) * 1.0)
    overhead_mean_mem = isolate_mean_mem / (clean_mean_mem * 1.0)
    overhead_mems = [isolate_mems[i]/(clean_mems[i]*1.0) for i in range(0, len(clean_mems))]

    print('\nAverage memory consumption')
    print(('#Websites: %d'%(len(clean_mems)))) 
    print(('\tclean: %.3f\tisolate: %.3f\toverhead: %.3f'%(clean_mean_mem, isolate_mean_mem, overhead_mean_mem)))
    print(('\tmax overhead: %.3f'%(max(overhead_mems))))
    print(('\tmin overhead: %.3f'%(min(overhead_mems))))
    overhead_len = len(overhead_mems)
    overhead_mems = sorted(overhead_mems)
    if overhead_len%2 == 0:
        target_index = overhead_len//2-1
        median = (overhead_mems[target_index] + overhead_mems[target_index+1]) / 2.0
    else:
        target_index = overhead_len//2
        median = overhead_mems[target_index]
    print(('\tmedian overhead: %.3f'%(median)))
    print('\n')




def usage():
    tab = '\t'
    print('Usage:')
    print((tab + 'python %s [OPTIONS]' % (__file__)))
    print((tab + '-d | --exp_dir='))
    print((tab*2 + 'Exp directory'))
    print((tab + '-u | --user_dir='))
    print((tab*2 + 'User directory of Chrome'))
    print((tab + '-n | --num='))
    print((tab*2 + 'Number of task splits, default is 512'))
    print((tab + '-p | --process='))
    print((tab*2 + 'Maximum number of processes, default is 8'))
    print((tab + '-s | --start'))
    print((tab*2 + 'Start index, default 0'))
    print((tab + '-e | --end'))
    print((tab*2 + 'End index, default number of URLs'))
    print((tab + '-t | --type='))
    print((tab*2 + 'Input type, [url2index|info2index2script] default "url2index"'))
    print((tab + '-o | --output_dir='))
    print((tab*2 + 'Output directory'))




if __name__ == '__main__':
    main(sys.argv[1:])
