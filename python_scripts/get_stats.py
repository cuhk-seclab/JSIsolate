import json, os, sys, traceback, getopt, tldextract
from urllib.parse import urlparse

def determine_script_privilege(url, first_party_domain):
    global extract
    
    try:
        script_priv = -1
        ta, tb, tc = extract(url)
        script_domain = tb + '.' + tc
        
        if script_domain == first_party_domain:
            script_priv = 1
        else:
            script_priv = 3
    except Exception as e:
        pass
    return script_priv



def measure(user_dir, task_id, start, end):
    global rank2type2info, extract, rank2script2cnt

    current_pid = os.getpid()
    current_dir = os.getcwd()

    input_dir = user_dir + '_logs_collect'
    try:
        files = os.listdir(input_dir)
    except Exception as e:
        print(e)
        return
    files =  [f for f in files if f.endswith('.configs')]

    for f in files:
        rank = f.split('.')[0]
        if rank not in rank2type2info:
            rank2type2info[rank] = {'3pto1p': list(), '1pto3p': list(), 'both': list(), '3': list(), 'cnt': 0, 'inline': 0, 'external': 0, 'static_3p': 0}
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'r') as input_f:
            url2configs = json.loads(input_f.read())
        for url, configs in list(url2configs.items()):
            try:
                ta, tb, tc = extract(url)
                first_party_domain = tb + '.' + tc
            except Exception as e:
                first_party_domain = url

            for config in configs:
                config_info = [info for key, info in list(config.items())]
                config_info.append(url)
                rank2type2info[rank]['cnt'] += 1 # count the number of static scripts
                if 'alter_match' in config:
                    # static inline
                    rank2type2info[rank]['inline'] += 1 # count the number of static inline scripts
                else:
                    # static external
                    rank2type2info[rank]['external'] += 1 # count the number of static external scripts
                    try:
                        ta, tb, tc = extract(config['match'])
                        script_domain = tb + '.' + tc
                    except Exception as e:
                        script_domain = config['match']
                    

                    if script_domain != first_party_domain:
                        rank2type2info[rank]['static_3p'] += 1
                        if config['world_id'] == "1":
                            rank2type2info[rank]['3pto1p'].append(config_info)
                    if script_domain == first_party_domain:
                        if config['world_id'] == '3':
                            rank2type2info[rank]['1pto3p'].append(config_info)

                if config['world_id'] == 'both':
                    rank2type2info[rank]['both'].append(config_info)
                if config['world_id'] == '3' and 'alter_match' not in config:
                    rank2type2info[rank]['3'].append(config_info)

    files = os.listdir(input_dir)
    files =  [f for f in files if f.endswith('.configs')]
    for f in files:
        rank = f.split('.')[0]
        input_file = os.path.join(input_dir, f)
        with open(input_file, 'r') as input_f:
            url2configs = json.loads(input_f.read())
        cnt = 0
        for url, configs in list(url2configs.items()):
            cnt += len(configs)
            for config in configs:

                if config['world_id'] == '3':
                    continue

                for s, infos in list(config['read'].items()):
                    if rank not in rank2script2cnt:
                        rank2script2cnt[rank] = dict()
                    if config['script_id'] not in rank2script2cnt[rank]:
                        rank2script2cnt[rank][config['script_id']]  = 0
                    
                    rank2script2cnt[rank][config['script_id']] += len(infos)

                for s, infos in list(config['read by'].items()):
                    if rank not in rank2script2cnt:
                        rank2script2cnt[rank] = dict()
                    if config['script_id'] not in rank2script2cnt[rank]:
                        rank2script2cnt[rank][config['script_id']]  = 0
                    correct_infos = [ii for ii in infos if not ii[-1]]
                    rank2script2cnt[rank][config['script_id']] += len(correct_infos)





def main(argv):
    global num_instances, rank2type2info, extract, rank2script2cnt

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


    
    rank2type2info = dict()
    rank2script2cnt = dict()
    extract = tldextract.TLDExtract(include_psl_private_domains=True)

    input_file = 'top-1m.csv'
    raw_data_dir = exp_dir

    with open('domain2revlist.json', 'r') as input_f:
        domain2revlist = json.loads(input_f.read())
    list_ranks = set()
    with open('top-1m.csv', 'r') as input_f:
        for line in input_f:
            line_split = line.split('\n')[0].split(',')
            rank = int(line_split[0])
            domain = line_split[1]
            if rank > 1000:
                break
            if domain not in domain2revlist:
                list_ranks.add(rank)
            elif len(domain2revlist[domain]) == 0:
                list_ranks.add(rank)

    try:
        os.chdir(exp_dir)
    except OSError as e:
        print(e)
        sys.exit(1)


    tasks = [i for i in range(num_instances-1, -1, -1)]
    for task in tasks:
        user_dir_group = '%s_%d' %(user_dir, task)
        try:
            measure(user_dir_group, task, start, end)
        except OSError as e:
            print(e)
            continue
    
    output_file = 'rank2type2info.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(rank2type2info))

    static_inline_cnt = 0
    static_external_cnt = 0
    static_external_3p_cnt = 0
    both_cnt = 0
    to1p_cnt = 0 # static from 3p domain but worldID is '1'
    three_world_cnt = 0 # static and worldID is '3'
    to3p_cnt = 0 # static from 1p domain but worldID is '3'


    static_inline_ranks = set()
    static_external_ranks = set()
    static_external_3p_ranks = set()
    both_ranks = set()
    to1p_ranks = set() # static from 3p domain but worldID is '1'
    three_world_ranks = set() # static and worldID is '3'
    to3p_ranks = set() # static from 1p domain but worldID is '3'


    to3p_rank2info = dict()
    to1p_rank2info = dict()

    for rank, type2info in list(rank2type2info.items()):
        #if int(rank) not in list_ranks:
        #    continue
        if int(rank) > end:
            continue
        if int(rank) < start:
            continue

        static_inline_cnt += type2info['inline']
        static_external_cnt += type2info['external']
        static_external_3p_cnt += type2info['static_3p']
        both_cnt += len(type2info['both'])
        three_world_cnt += len(type2info['3'])
        to3p_cnt += len(type2info['1pto3p'])
        to1p_cnt += len(type2info['3pto1p'])

        if type2info['inline'] > 0:
            static_inline_ranks.add(rank)
        if type2info['external'] > 0:
            static_external_ranks.add(rank)
        if type2info['static_3p'] > 0:
            static_external_3p_ranks.add(rank)
        if len(type2info['both']) > 0:
            both_ranks.add(rank)
        if len(type2info['3']) > 0:
            three_world_ranks.add(rank)
        if len(type2info['3pto1p']) > 0:
            to1p_ranks.add(rank)
            to1p_rank2info[rank] = type2info['3pto1p']


        if len(type2info['1pto3p']) > 0:
            to3p_ranks.add(rank)
            to3p_rank2info[rank] = type2info['1pto3p']
            
    output_file = '1pto3p_rank2info.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(to3p_rank2info))
    
    output_file = '3pto1p_rank2info.json'
    output_file = os.path.join(output_dir, output_file)
    with open(output_file, 'w') as output_f:
        output_f.write(json.dumps(to1p_rank2info))



    print('\n\n')
    #print('Static inline\t#scripts: %d\t#websites: %d'%(static_inline_cnt, len(static_inline_ranks))) cannot be policies for them
    print(('Static external\t#scripts: %d\t#websites: %d'%(static_external_cnt, len(static_external_ranks))))
    print(('Static external 3p\t#scripts: %d\t#websites: %d'%(static_external_3p_cnt, len(static_external_3p_ranks))))

    print(('Context is 3p\t#scripts: %d\t#websites: %d'%(three_world_cnt, len(three_world_ranks))))
    print(three_world_ranks)

    print(('Static from 3p domain but context is 1p\t#scripts: %d\t#websites: %d'%(to1p_cnt, len(to1p_ranks)))) 
    print(('Static from 1p domain but context is 3p\t#scripts: %d\t#websites: %d'%(to3p_cnt, len(to3p_ranks)))) 

    print(('Static and context is both\t#scripts: %d\t#websites: %d'%(both_cnt, len(both_ranks)))) 
    print(both_ranks)

    

    total_cnt = 0
    total_script_cnt = 0
    total_ranks = set()
    for rank, script2cnt in list(rank2script2cnt.items()):
        #if int(rank) not in list_ranks:
        #    continue
        if int(rank) > end:
            continue
        if int(rank) < start:
            continue
        total_ranks.add(rank)
        for script, cnt in list(script2cnt.items()):
            total_script_cnt += 1
            total_cnt += cnt
    print(('#Ranks: %d'%(len(total_ranks))))
    print(('#Script: %d'%(total_script_cnt)))
    print(('#Accesses: %d'%(total_cnt)))



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
    print((tab + '-o | --output_dir'))
    print((tab*2 + 'Output directory'))




if __name__ == '__main__':
    main(sys.argv[1:])
