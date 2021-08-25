import codecs, json, re, time, os, getopt, traceback 
import signal, psutil, tldextract
from multiprocessing import Process as Task, Queue
import multiprocessing as mp
import sys, shutil 
from urllib.parse import urlparse




internal_props = {'window':['closed', 'console', 'defaultStatus', 'document', 'frameElement', 'frames', 'history', 
                            'innerHeight', 'innerWidth', 'length', 'localStorage', 'location', 'name', 'navigator', 
                            'opener', 'outerHeight', 'outerWidth', 'pageXOffset', 'pageYOffset', 'parent', 'screen',
                            'screenLeft', 'screenTop', 'screenX', 'screenY', 'sessionStorage', 'self', 'status', 'top'], 
                  'document':["activeElement", "anchors", "applets", "baseURI", "body", "cookie", "charset", "characterSet", 
                              "defaultView", "designMode", "doctype", "documentElement", "documentMode", "documentURI", 
                              "domain", "embeds", "forms", "fullscreenElement", "head", "images", "implementation", 
                              "inputEncoding", "lastModified", "links", "readyState", "referrer", "scripts", 
                              "strictErrorChecking", "title", "URL"]}

internal_methods = {'window':['alert', 'atob', 'blur', 'btoa', 'clearInterval', 'clearTimeout', 'clearTimeout', 'close',  
                              'confirm', 'focus', 'getComputedStyle', 'matchMedia', 'moveBy', 'moveTo', 'open', 'print',  
                              'prompt', 'resizeBy', 'resizeTo', 'scrollBy', 'scrollTo', 'setInterval', 'setTimeout', 'stop'],
                    'document':["addEventListener", "adoptNode", "close", "createAttribute", "createComment", 
                                "createDocumentFragment", "createElement", "createEvent", "createTextNode", 
                                "execCommand", "fullscreenEnabled", "getElementById", "getElementsByClassName", 
                                "getElementsByName", "getElementsByTagName", "hasFocus", "importNode", 
                                "normalize", "normalizeDocument", "open", "querySelector", "querySelectorAll", 
                                "removeEventListener", "renameNode", "write", "writeln"]}

primitive_type_values = ['undefined', 'null', 'true', 'false', 'BigInt', 'String', 'Symbol']

builtin_names = ['Object', 'Function', 'Boolean', 'Symbol', 'Error', 'AggregateError', 'EvalError', 'InternalError', 'RangeError', 'ReferenceError', 'SyntaxError', 'TypeError', 'URIError', 'Number', 'BigInt', 'Math', 'Date', 'String', 'RegExp', 'Array', 'Int8Array', 'Uint8Array', 'Uint8ClampedArray', 'Int16Array', 'Uint16Array', 'Int32Array', 'Uint32Array', 'Float32Array', 'Float64Array', 'BigInt64Array', 'BigUint64Array', 'Map', 'Set', 'WeakMap', 'WeakSet', 'ArrayBuffer', 'SharedArrayBuffer', 'Atomics', 'DataView', 'JSON', 'Promise', 'Generator', 'GeneratorFunction', 'AsyncFunction', 'Iterator', 'AsyncIterator', 'Reflect', 'Proxy', 'Intl', 'WebAssembly']


def getlocaltime():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

# This function tries to ensure that no extra zombie children stick around
def kill_child_processes(parent_pid=None, parent=None, timeout=3, sig=signal.SIGTERM, include_parent = True):
    global log_f
    #current_time = getlocaltime()
    if not parent and not parent_pid:
        return (None, None)
    try:
        if not parent and parent_pid:
            parent = psutil.Process(parent_pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return (None, None)
    if parent.pid == os.getpid():
        include_parent = False
    children = parent.children(recursive=True)
    if include_parent:
        children.append(parent)
    for process in children:
        #msg = '%s\tKilling child process [%d] of [%d]...\n' % (current_time, process.pid, parent.pid)
        #if log_f:
            #log_f.write(msg)
        try:
            process.send_signal(sig)
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            pass
    gone, alive = psutil.wait_procs(children, timeout=timeout, callback=None)
    if alive:
        for process in alive:
            try:
                process.kill() # SEND SIGKILL
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                pass
        gone, alive = psutil.wait_procs(alive, timeout=timeout, callback=None)
    return (gone, alive)

def get_child_processes(parent_pid):
    try:
        parent = psutil.Process(parent_pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        return None
    children = parent.children(recursive=True)
    return children

def signal_term_handler(sig, frame):
    global parent_pid
    current_pid = os.getpid()
    if current_pid == parent_pid:
        #msg = '%s\tPARENT PROCESS [%d] received SIGTERM!!! Killing all child processes...\n' % (current_time, current_pid)
        process_name = 'chrome'
        kill_processes_by_name(process_name)
    kill_all_processes()

def kill_all_processes(restart_parent_flag=False):
    global parent_pid, process_list, log_f
    current_time = getlocaltime()
    current_pid = os.getpid()
    if current_pid == parent_pid:
        msg = '%s\tPARENT PROCESS [%d] received SIGTERM!!! Killing all child processes...\n' % (current_time, current_pid)
    else:
        msg = '%s\tProcess [%d] received SIGTERM!!! Killing all child processes... PARENT PID=[%d]\n' % (current_time, current_pid, parent_pid)
    #print(msg)
    #sys.stdout.flush()
    log_f.write(msg)
    kill_child_processes(parent_pid = current_pid)
    current_time = getlocaltime()
    msg = '%s\tAll child processes of Process [%d] are killed!!!\n' % (current_time, current_pid)
    #print(msg)
    log_f.write(msg)
    if current_pid == parent_pid:
        if restart_parent_flag:
            restart_all_tasks(log_f)
        else:
            log_f.close()
    sys.exit()

def get_static_scripts(id2url_f, id2parent_f):
    forced_first_party_scripts = list() # only 1 script in a context, no need to analyze, directly assign to first-party world
    sid2cid = dict()
    cid2frameurl = dict()
    frameurl2cid = dict()

    sid2frameurl = dict()
    script2parent = dict()

    with open(id2parent_f, 'r')  as input_f:
        cnt = 0
        for line in input_f:
            cnt += 1
            split_list = line.split('\n')[0].split(',')
            script_id = int(split_list[0])
            parent_id = split_list[1]
            frame_url = split_list[2][1:-1]
            if script_id not in sid2frameurl:
                sid2frameurl[script_id] = set()
            sid2frameurl[script_id].add((cnt, frame_url))
            if (script_id, frame_url) not in script2parent:
                script2parent[(script_id, frame_url)] = parent_id

    script2url = dict()
    with open(id2url_f, 'r') as input_f:
        cnt = 0
        for line in input_f:
            cnt += 1
            split_list = line.split('\n')[0].split('\t')
            script_id = int(split_list[0])
            script_url = split_list[1]
            context_id = int(split_list[2].split()[0], 16)
            if script_id not in sid2cid:
                sid2cid[script_id] = set()
            sid2cid[script_id].add((cnt, context_id))

            if not script_url.startswith('http'):
                script_source_f = '.'.join(id2url_f.split('.')[0:3]) + '.' + str(script_id) + '.script'
                try:
                    with open(script_source_f, 'r') as input_ssf:
                        for line_ss in input_ssf:
                            script_url = line_ss.split()[0]
                            if script_url.startswith('0x'):
                                script_url = ''
                            break
                except Exception as e:
                    pass
            script2url[(script_id, context_id)] = script_url

        cid2sid = dict()
        for sid, cids in list(sid2cid.items()):
            for cid in cids:
                if cid[1] not in cid2sid:
                    cid2sid[cid[1]] = set()
                cid2sid[cid[1]].add(sid)

        for cid, sids in list(cid2sid.items()):
            if len(sids) == 1: # only 1 script in cid
                forced_first_party_scripts.append((cid, list(sids)[0]))

        for sid, cids in sorted(list(sid2cid.items()), key=lambda t:t[0]):
            if len(cids) > 1:
                # script id shared in multiple frames
                # now check if the context contain other scripts with non-shared sid
                for cid in sorted(cids, key=lambda t:t[0]):
                    if (cid[1], sid) in forced_first_party_scripts:
                        continue
                    other_sids = cid2sid[cid[1]]
                    non_shared_sid = None
                    for ssid in sorted(other_sids):
                        if len(sid2cid[ssid]) == 1 and ssid in sid2frameurl:
                            non_shared_sid  = ssid
                            break
                    if non_shared_sid is not None:
                        # we now use non_shared_sid to determine the frame url for cid
                        frame_urls = sorted(sid2frameurl[non_shared_sid], key=lambda t:t[0])
                        if cid not in cid2frameurl:
                            cid2frameurl[cid] = list(frame_urls)[0][1]
                    else:
                        correct_frame_url = None
                        for ssid in sorted(other_sids):
                            if ssid in sid2frameurl and len(sid2frameurl[ssid]) == 1:
                                correct_frame_url = sorted(list(sid2frameurl[ssid]), key=lambda t:t[0])[0][1]
                                break
                        if correct_frame_url is not None:
                            if cid not in cid2frameurl:
                                cid2frameurl[cid] = correct_frame_url
                        else:
                            # page navigates, same script id appears in multiple tabs 
                            # and corresponds to multiple frame urls
                            # we use the first URL as the frame url, which shall be the initial page 
                            correct_frame_url = None
                            for ssid in sorted(other_sids):
                                if ssid in sid2frameurl:
                                    correct_frame_url = sorted(list(sid2frameurl[ssid]), key=lambda t:t[0])[0][1]
                                    break

                            if correct_frame_url is not None:
                                if cid not in cid2frameurl:
                                    cid2frameurl[cid] = correct_frame_url
                        
            else:
                # script id only used in one context
                if sid not in sid2frameurl:
                    # could be an event listener or JS url or eval-generated code
                    # handled separately
                    continue
                else:
                    if len(sid2frameurl[sid]) > 1:
                        # sid appears in multiple tabs
                        # let's use other sid to determine the exact frame url
                        min_cid = sorted(list(cids), key=lambda t:t[0])[0]#[1]
                        ssids = cid2sid[min_cid[1]]
                        correct_frame_url = None
                        for ssid in sorted(ssids):
                            if ssid in sid2frameurl and len(sid2frameurl[ssid]) == 1:
                                correct_frame_url = sorted(list(sid2frameurl[ssid]), key=lambda t:t[0])[0][1]
                                break
                        if correct_frame_url is None:
                            pass
                        else:
                            if min_cid not in cid2frameurl:
                                cid2frameurl[min_cid] = correct_frame_url
                    else:
                        min_cid = sorted(list(cids), key=lambda t:t[0])[0]#[1]
                        if min_cid not in cid2frameurl:
                            cid2frameurl[min_cid] = sorted(list(sid2frameurl[sid]), key=lambda t:t[0])[0][1]
    
    
    for cid, url in list(cid2frameurl.items()): # cid: (cnt, context_id)
        if url not in frameurl2cid:
            frameurl2cid[url] = list()
        frameurl2cid[url].append(cid)

    unique_frameurl2cid = dict()
    for url, cids in list(frameurl2cid.items()):
        min_cid = sorted(cids, key=lambda t:t[0])[0][1]
        unique_frameurl2cid[url] = min_cid
    static_script_ids = list()
    for script, parent in list(script2parent.items()):
        script_id = int(script[0])
        frame_url = script[1]
        try:
            context_id = unique_frameurl2cid[frame_url]
        except Exception as e:
            continue
        if parent == '<null>':
            static_script_ids.append((context_id, script_id))

    static_id2url = dict() # (context_id, script-id) -> script_url
    for script, url in list(script2url.items()):
        script_id = int(script[0])
        context_id = script[1]
        if (context_id, script_id) in static_script_ids:
            static_id2url[(context_id, script_id)] = url

    for script in static_script_ids:
        try:
            if script not in static_id2url:
                context_id = script[0]
                script_id = int(script[1])
                script_file = '/'.join(id2url_f.split('/')[:-1]) + '/' + '.'.join(id2url_f.split('/')[-1].split('.')[:-1]) + '.' + str(script_id) + '.script'
                try:
                    with open(script_file, 'r') as input_f:
                        for line in input_f:
                            script_url = line.split('\n')[0].split()[0]
                            if script_url.startswith('0x'):
                                script_url = ''
                            break
                        static_id2url[script] = script_url
                except Exception as e:
                    pass
        except Exception as e:
            print((script, static_id2url))

    unique_cid2frameurl = dict()
    for frameurl, cid in sorted(list(unique_frameurl2cid.items()), key=lambda t:t[0], reverse=True):
        unique_cid2frameurl[cid] = frameurl
    frame2url = dict() # (context_id) -> (frame_url, frame_domain)
    for cid, frameurl in list(unique_cid2frameurl.items()):
        try:
            ta, tb, tc = extract(frameurl)
            frame_domain = tb + '.' + tc
        except Exception as e:
            frame_domain = frameurl
        frame2url[cid] = (frameurl, frame_domain)

    
    return static_script_ids, static_id2url, frame2url, forced_first_party_scripts




def determine_script_privilege(url, first_party_domain):
    global extract
    try:
        script_priv = -1
        ta, tb, tc = extract(url)
        script_domain = tb + '.' + tc
        ta, tb, tc = extract(first_party_domain)
        first_party_domain = tb + '.' + tc

        if script_domain == first_party_domain:
            script_priv = 1
        else:
            script_priv = 3
    except Exception as e:
        pass
    if url == '':
        script_priv = 1
    return script_priv




def measure(user_dir, task_id, length, start, end, status_queue, process_index):
    global processed_data_dir, extract, domain2revdomains

    current_pid = os.getpid()
    current_dir = os.getcwd()
    try:
        status = 'Process %-4d task %d/%d PID [%d] starting ...' % (process_index, task_id+1, length, current_pid)
        status_queue.put([process_index, status])

        result_dict = dict()
        processed_list = set()

        raw_input_dir = user_dir + '_logs_collect'
        input_dir = os.path.join(current_dir, raw_input_dir)
        file_list = os.listdir(input_dir)
        rank2access_files = dict()
        rank2frame2url = dict()
        for f in file_list:
            if f.endswith('.access'):
                split_list = f.split('.')
                rank = int(split_list[0])
                
                if rank not in rank2access_files:
                    rank2access_files[rank] = list()
                rank2access_files[rank].append(f)


        output_dir = os.path.join(processed_data_dir, raw_input_dir)
        raw_output_dir = os.path.join(processed_data_dir, raw_input_dir)

        if not os.path.isdir(raw_output_dir):
            os.mkdir(raw_output_dir)
        rank2url2configs = dict()

        for rank, func_files in list(rank2access_files.items()):
            if rank > end:
                continue
            if rank % num_instances != task_id or rank in processed_list or rank < start:
                continue
            try:
                for task in func_files:
                    try:
                        mid_str = '.'.join(task.split('.')[:-1])
                        script2group = dict()
                        script2reads = dict() # for each script, record a set of scripts that reads it
                        script2read2infos = dict() # script -> script that reads it -> read info
                        script2builtinwrites = dict()
                        next_group_id = 0
                        write_context2target2info = dict()
                        conflict_context2target2info = dict()

                        task_file = os.path.join(input_dir, task)
                        id2url_file = mid_str + '.id2url'
                        id2url_file = os.path.join(input_dir, id2url_file)
                        id2parentid_file = mid_str + '.id2parentid'
                        id2parentid_file = os.path.join(input_dir, id2parentid_file)
                        script_files = os.listdir(input_dir)
                        script_files = [f for f in script_files if f.endswith('.script') and f.startswith(mid_str)]
                       
                        try:
                            static_script_ids, static_id2url, frame2url, forced_first_party_scripts = get_static_scripts(id2url_file, id2parentid_file)
                        except Exception as e:
                            continue

                        with open(task_file, 'r') as input_f:
                            for line in input_f:
                                try:
                                    line = line.split('\n')[0]
                                    line_split = line.split(',obj__dep,')
                                    if line_split[0] == '[R]':
                                        #[R], time_stamp, script_id, receiver, name, native_context
                                        time_stamp = float(line_split[1])
                                        script_id = int(line_split[2])
                                        receiver_info = line_split[3]
                                        name_info = line_split[4]
                                        context_info = line_split[5]
                                        receiver_id = receiver_info.split('<')[0].split()[0]
                                        name_id = name_info.split('<')[0].split()[0]
                                        context_id = int(context_info.split()[0], 16)
                                        if (context_id, script_id) not in static_script_ids:
                                            continue
                
                                        if (context_id, script_id) not in script2group:
                                            script2group[(context_id, script_id)] = next_group_id
                                            next_group_id += 1

                                        if context_id not in write_context2target2info:
                                            continue
                                        if '<' in receiver_info and '>' in receiver_info:
                                            if receiver_info.split('<')[1].split()[0] == 'Window':
                                                receiver_id = None
                                            elif receiver_info.split('<')[1].split('>')[0] == 'JSGlobal Object':
                                                receiver_id = None
                                            else:
                                                receiver_id = receiver_info.split()[0]
                                        else:
                                            receiver_id = receiver_info
                
                                        name_split = name_info.split('<')[-1].split('>')[0].split()


                                        if len(name_split) >= 1 and name_split[0] == 'Symbol:':
                                            #print('[R]', name_info, receiver_info)
                                            continue


                                        if len(name_split) >= 2:
                                            read_name = name_split[1]
                                        else:
                                            read_name = ' '
                                        if receiver_id is None: # reading window.xxx
                                            if read_name in internal_props['window'] or read_name in internal_methods['window']:
                                                continue
                                        elif '<' in receiver_info and '>' in receiver_info and receiver_info.split('<')[1].split()[0] == 'HTMLDocument': # reading document.xxx
                                            if read_name in internal_props['document'] or read_name in internal_methods['document']:
                                                continue


                                        if receiver_id is not None:
                                            read_target = receiver_id + '.' + read_name
                                        else:
                                            read_target = read_name
                  
                                        if read_target in write_context2target2info[context_id]:
                                            write_info = write_context2target2info[context_id][read_target]
                                            write_info += (read_target,)
                                            # write_info: (script_id, time_stamp, write_value, write_type)
                                            write_script_id = write_info[0]
                                            if script_id != write_script_id:
                                                if (context_id, write_script_id) not in script2reads:
                                                    script2reads[(context_id, write_script_id)] = set()
                                                script2reads[(context_id, write_script_id)].add((context_id, script_id))

                                                    
                                                if (context_id, write_script_id) not in script2read2infos:
                                                    script2read2infos[(context_id, write_script_id)] = dict()
                                                script2read2infos[(context_id, write_script_id)][(context_id, script_id)] = list()
                                                script2read2infos[(context_id, write_script_id)][(context_id, script_id)].append(write_info)


                                                group_id = script2group[(context_id, script_id)]
                                                write_group_id = script2group[(context_id, write_script_id)]
                                                if group_id == write_group_id:
                                                    continue
                                                new_group_id = min(group_id, write_group_id)
                                                old_group_id = max(group_id, write_group_id)
                                                for script, group in list(script2group.items()):
                                                    if group == old_group_id:
                                                        script2group[script] = new_group_id
                                        else:
                                            #print('read before write', read_target, script_id)
                                            pass




                                    elif line_split[0] == '[W]':
                                        #[W], time_stamp, script_id, receiver, name, value, native_context
                                        time_stamp = float(line_split[1])
                                        script_id = int(line_split[2])
                                        receiver_info = line_split[3]
                                        name_info = line_split[4]
                                        value_info = line_split[5]
                                        context_info = line_split[6]
                                        receiver_id = receiver_info.split('<')[0].split()[0]
                                        context_id = int(context_info.split()[0], 16)
                                        if (context_id, script_id) not in static_script_ids:
                                            continue

                                        if (context_id, script_id) not in script2group:
                                            script2group[(context_id, script_id)] = next_group_id
                                            next_group_id += 1

                                        name_split = name_info.split('<')[-1].split('>')[0].split()


                                        if len(name_split) >= 1 and name_split[0] == 'Symbol:':
                                            #print('[W]', receiver_info, name_info, value_info)
                                            continue

                                        if len(name_split) >= 2:
                                            write_name = name_split[1]
                                        else:
                                            write_name = ' '

                                        if '<' in receiver_info and '>' in receiver_info:
                                            if receiver_info.split('<')[1].split()[0] == 'Window':
                                                receiver_id = None
                                            elif receiver_info.split('<')[1].split('>')[0] == 'JSGlobal Object':
                                                receiver_id = None
                                            else:
                                                receiver_id = receiver_info.split()[0]
                                        else:
                                            receiver_id = receiver_info

                                        if '<' in value_info and '>' in value_info:
                                            potential_name_list = value_info.split('<')[1].split()
                                            if len(potential_name_list) > 1:
                                                potential_name = potential_name_list[1]
                                                if potential_name.split('.')[0] in builtin_names:
                                                    if (context_id, script_id) not in script2builtinwrites:
                                                        script2builtinwrites[(context_id, script_id)] = list()
                                                    builtin_write = (potential_name, script_id, receiver_id, line)
                                                    script2builtinwrites[(context_id, script_id)].append(builtin_write)

                                        if '<' in value_info and '>' in value_info:
                                            value_id = value_info.split('<')[0].split()[0]
                                            value_type = value_info.split('<')[1].split()[0].split('>')[0].split('[')[0]
                                            if value_type not in primitive_type_values:
                                                write_value = value_id
                                                if value_type == 'JSFunction':
                                                    write_type = 'function'
                                                else:
                                                    write_type = 'object'
                                            else:
                                                # all primitive types
                                                write_value = value_info.split('<')[1].split('>')[0]
                                                if value_type == 'undefined':
                                                    write_type = 'undefined'
                                                elif value_type == 'null':
                                                    write_type = 'object'
                                                elif value_type == 'true' or value_type == 'false':
                                                    write_type = 'boolean'
                                                elif value_type == 'BigInt':
                                                    write_type = 'bigint'
                                                elif value_type == 'Symbol':
                                                    write_type = 'symbol'
                                                else: # value_type == 'String':
                                                    write_type = 'string'

                                        else:
                                            # could only be numbers / Symbol
                                            write_value = value_info
                                            write_type = 'number'
                
                                        if context_id not in write_context2target2info:
                                            write_context2target2info[context_id] = dict()
                                        if receiver_id is not None:
                                            write_target = receiver_id + '.' + write_name
                                        else:
                                            write_target = write_name
                                        if write_target in write_context2target2info[context_id]:
                                            prev_write_info = write_context2target2info[context_id][write_target]
                                            # prev_write_info = (script_id, time_stamp, write_value, write_type)
                                            prev_script_id = prev_write_info[0]
                                            prev_time_stamp = prev_write_info[1]
                                            prev_write_value = prev_write_info[2]
                                            prev_write_type = prev_write_info[3]
                                            if prev_script_id != script_id:
                                                conflict_type = None
                                                if write_type != prev_write_type:
                                                    conflict_type = 'type'
                                                elif write_value != prev_write_value:
                                                    if write_type == 'function':
                                                        conflict_type = 'function'
                                                    else:
                                                        conflict_type = 'value'
                                                else: # same type and same value, perhaps duplicate
                                                    pass
                                                    #conflict_type = 'duplicate'
                                                if conflict_type is not None:
                                                    if context_id not in conflict_context2target2info:
                                                        conflict_context2target2info[context_id] = dict()
                                                    if write_target not in conflict_context2target2info[context_id]:
                                                        conflict_context2target2info[context_id][write_target] = set()
                                                    conflict_info = (conflict_type, script_id, time_stamp, write_value, write_type, prev_script_id, prev_time_stamp, prev_write_value, prev_write_type)
                                                    conflict_context2target2info[context_id][write_target].add(conflict_info)

                                        write_context2target2info[context_id][write_target] = (script_id, time_stamp, write_value, write_type)


                
                                    else:
                                        # currently we have only 2 types of logs, [R]/[W]
                                        pass

                                except Exception as e:
                                    try:
                                         exc_type, exc_value, exc_traceback = sys.exc_info()
                                         lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                                         print((''.join('!! ' + line for line in lines)))
                                         sys.stdout.flush()
                                    except Exception:
                                         pass

                            group2scripts = dict()
                            for script, group in list(script2group.items()):
                                if group not in group2scripts:
                                    group2scripts[group] = set()
                                group2scripts[group].add(script)


                            script2writes = dict() # for each script, record a set of scripts that it reads
                            script2write2infos = dict() # script -> script that it reads -> read info
                            for script in static_script_ids:
                                if script not in script2reads:
                                    # this script is never read by other scripts, we record an empty set for it
                                    script2reads[script] = set()

                            for script, reads in list(script2reads.items()):
                                for read in reads:
                                    if read not in script2writes:
                                        script2writes[read] = set()
                                    script2writes[read].add(script)
                            for script in static_script_ids:
                                if script not in script2writes:
                                    # this script never reads other scripts, we record an empty set for it
                                    script2writes[script] = set()

            

                            for script in static_script_ids:
                                if script not in script2read2infos:
                                    script2read2infos[script] = dict()
                            for script, read2infos in list(script2read2infos.items()):
                                for read, infos in list(read2infos.items()):
                                    if read not in script2write2infos:
                                        script2write2infos[read] = dict()
                                    script2write2infos[read][script] = infos
                            for script in static_script_ids:
                                if script not in script2write2infos:
                                    script2write2infos[script] = dict()



            
                            first_party_scripts = list()
                            both_scripts = list()
                            third_party_scripts = list()
                            priv2scripts = {'1': set(), '3': set(), 'both': set()}
                            for script in static_script_ids:
                                context_id = script[0]
                                script_id = int(script[1])
                                first_party_urls = frame2url[context_id]#[1]
                                first_party_domain = first_party_urls[0]
                                try:
                                    script_priv = determine_script_privilege(static_id2url[script], first_party_domain)
                                except Exception as e:
                                    continue
                                if script_priv == 1 or script in forced_first_party_scripts:
                                    priv2scripts['1'].add(script)
                                    first_party_scripts.append(script)
                                else:
                                    try:
                                        ta, tb, tc = extract(first_party_domain)
                                        website_domain = tb + '.' + tc
                                    except Exception as e:
                                        website_domain = first_party_domain
                                    try:
                                        script_url_ = static_id2url[script]
                                    except Exception as e:
                                        continue
                                    try:
                                        ta, tb, tc = extract(script_url_)
                                        script_domain_ = tb + '.' + tc
                                    except Exception as e:
                                        script_domain_ = script_url_

                                    if website_domain in domain2revdomains:
                                        rev_domains = domain2revdomains[website_domain]
                                        if script_domain_ in rev_domains:
                                            #correct_config['world_id'] = '1'
                                            priv2scripts['1'].add(script)
                                            first_party_scripts.append(script)

                            processed_scripts = list()
                            to_be_determined = list()
                            propagate_queue = first_party_scripts
                            while len(propagate_queue) > 0:
                                script = propagate_queue[0]
                                propagate_queue = propagate_queue[1:] # pop script
                                processed_scripts.append(script)
                                for read in script2reads[script]:
                                    if read in processed_scripts:
                                        continue
                                    if read not in first_party_scripts:
                                        # not reading others && is read by multiple scripts
                                        if len(script2writes[read]) == 0 and len(script2reads[read]) > 1:
                                            to_be_determined.append(read)
                                        else:
                                            first_party_scripts.append(read)
                                            priv2scripts['1'].add(read)
                                            propagate_queue.append(read)
                                for write in script2writes[script]:
                                    if write in processed_scripts:
                                        continue
                                    if write not in first_party_scripts:
                                        if len(script2writes[write]) == 0 and len(script2reads[write]) > 1:
                                            to_be_determined.append(write)
                                        else:
                                            first_party_scripts.append(write)
                                            priv2scripts['1'].add(write)
                                            propagate_queue.append(write)



                            for script in static_script_ids:
                                if script not in first_party_scripts and script not in to_be_determined:
                                    # can only be 3p
                                    third_party_scripts.append(script)
                                    priv2scripts['3'].add(script)
                                    

                            # We may have misclassified some scripts: 'both' -> '1p'
                            # Now fix this
                            for script in to_be_determined:
                                if len(script2writes[script]) == 0:
                                    found_third_read = False
                                    found_first_read = False
                                    for read in script2reads[script]:
                                        if read in third_party_scripts:
                                            found_third_read = True
                                        else:
                                            found_first_read = True
                                    if found_third_read and found_first_read:
                                        priv2scripts['both'].add(script)
                                        both_scripts.append(script)
                                    else:
                                        priv2scripts['1'].add(script)
                                        first_party_scripts.append(script)



                            #'''
                            found_new_trusted_domain = True
                            while found_new_trusted_domain:
                                found_new_trusted_domain = False

                                cid2trusted_domains = dict()
                                for priv, scripts1 in list(priv2scripts.items()):
                                    if priv != '1':
                                        continue
                                    for script1 in scripts1:
                                        try:
                                            script_url1 = static_id2url[script1]
                                        except Exception as e1:
                                            continue
                                        try:
                                            ta, tb, tc =  extract(script_url1)
                                            script_domain1 = tb +'.'+tc
                                        except Exception as e:
                                            script_domain1 = script_url1
                                        cid = script1[0]
                                        if cid not in cid2trusted_domains:
                                            cid2trusted_domains[cid] = set()
                                        cid2trusted_domains[cid].add(script_domain1)
                                old_cnt = 0
                                for cid, trusted_domains in list(cid2trusted_domains.items()):
                                    old_cnt += len(trusted_domains)

                                to1p = set()
                                for priv, scripts in list(priv2scripts.items()):
                                    if priv != '3':
                                        continue
                                    for script in scripts:
                                        try:
                                            script_url1 = static_id2url[script]
                                        except Exception as e2:
                                            continue
                                        try:
                                            ta, tb, tc =  extract(script_url1)
                                            script_domain1 = tb +'.'+tc
                                        except Exception as e:
                                            script_domain1 = script_url1
                                        if script[0] in cid2trusted_domains and script_domain1 in cid2trusted_domains[script[0]]:
                                            to1p.add(script)
                                for script in to1p:
                                    try:
                                        priv2scripts['3'].remove(script)
                                        third_party_scripts.remove(script)
                                    except  Exception as e:
                                        pass
                                    priv2scripts['1'].add(script)
                                    first_party_scripts.append(script)



                                processed_scripts = list()
                                to_be_determined = list()
                                propagate_queue = first_party_scripts
                                while len(propagate_queue) > 0:
                                    script = propagate_queue[0]
                                    propagate_queue = propagate_queue[1:] # pop script
                                    processed_scripts.append(script)
                                    for read in script2reads[script]:
                                        if read in processed_scripts:
                                            continue
                                        if read not in first_party_scripts:
                                            # not reading others && is read by multiple scripts
                                            if len(script2writes[read]) == 0 and len(script2reads[read]) > 1:
                                                to_be_determined.append(read)
                                            else:
                                                first_party_scripts.append(read)
                                                priv2scripts['1'].add(read)
                                                propagate_queue.append(read)
                                    for write in script2writes[script]:
                                        if write in processed_scripts:
                                            continue
                                        if write not in first_party_scripts:
                                            if len(script2writes[write]) == 0 and len(script2reads[write]) > 1:
                                                to_be_determined.append(write)
                                            else:
                                                first_party_scripts.append(write)
                                                priv2scripts['1'].add(write)
                                                propagate_queue.append(write)


                                # some scripts might be changed from 3p->1p during the 2nd propagation
                                # now validate 'both' scripts again
                                real_both_scripts = list()
                                for script in both_scripts:
                                    found_third_read = False
                                    found_first_read = False
                                    for read in script2reads[script]:
                                        if read in third_party_scripts:
                                            found_third_read = True
                                        else:
                                            found_first_read = True
                                        if found_third_read and found_first_read:
                                            real_both_scripts.append(script)

                                for script in both_scripts:
                                    if script not in real_both_scripts:
                                        try:
                                            priv2scripts['both'].remove(script)
                                        except Exception as e:
                                            pass
                                        try:
                                            priv2scripts['1'].add(script)
                                        except Exception as e:
                                            pass
                                new_cid2trusted_domains = dict()
                                for priv, scripts1 in list(priv2scripts.items()):
                                    if priv != '1':
                                        continue
                                    for script1 in scripts1:
                                        try:
                                            script_url1 = static_id2url[script1]
                                        except Exception as e3:
                                            continue
                                        try:
                                            ta, tb, tc =  extract(script_url1)
                                            script_domain1 = tb +'.'+tc
                                        except Exception as e:
                                            script_domain1 = script_url1
                                        cid = script1[0]
                                        if cid not in new_cid2trusted_domains:
                                            new_cid2trusted_domains[cid] = set()
                                        new_cid2trusted_domains[cid].add(script_domain1)
                                new_cnt = 0
                                for cid, trusted_domains in list(new_cid2trusted_domains.items()):
                                    new_cnt += len(trusted_domains)
                                if new_cnt > old_cnt:
                                    found_new_trusted_domain = True

                            url2configs = dict()
                            for priv, scripts in list(priv2scripts.items()):
                                world_id = str(priv)
                                for script in scripts:
                                    config = dict() #{'world_id': -1, condition:}
                                    config['read'] = dict()
                                    config['read by'] = dict()
                                    config["world_id"] = world_id
                                    config["script_id"] = script[1]
                                    try:
                                        script_url = static_id2url[script]
                                    except Exception as e:
                                        continue
                                  
                                    script_id = script[1]
                                    context_id = script[0]
                                    if context_id not in frame2url:
                                        continue

                                    try:
                                        first_party_domain = frame2url[context_id][0]#[1]
                                    except Exception as e:
                                        print(e)
                                    script_priv = determine_script_privilege(static_id2url[script], first_party_domain)

                                    for write in script2writes[script]: # write: scripts that are read by the current script
                                        write_priv = determine_script_privilege(static_id2url[write], first_party_domain)
                                        if script_priv != 1: # current_script (3) read 1, or current_script (3) read 3
                                            # [script] reads [write]
                                            if write not in config['read']:
                                                config['read'][str(write)] = list()
                                            if script_priv != 1 and write_priv != 1:
                                                duplicate = True
                                            else:
                                                duplicate = False
                                            for info in script2write2infos[script][write]:
                                                info += (duplicate,)
                                                config['read'][str(write)].append(info)
                                    for read in script2reads[script]: # read: scripts that read the current script
                                        read_priv = determine_script_privilege(static_id2url[read], first_party_domain)
                                        if script_priv != 1:
                                            if read not in config['read by']:
                                                config['read by'][str(read)] = list()
                                            if script_priv != 1 and read_priv != 1:
                                                duplicate = True
                                            else:
                                                duplicate = False
                                            for info in script2read2infos[script][read]:
                                                info += (duplicate,)
                                                config['read by'][str(read)].append(info)



                                  
                                    script_id = script[1]
                                    context_id = script[0]
                                    if context_id not in frame2url:
                                        continue
                                    frame_url = frame2url[context_id][0]
                                    if frame_url not in url2configs:
                                        url2configs[frame_url] = list()
                                        

                                    script_origin = urlparse(script_url).scheme + '://' + urlparse(script_url).netloc
                                    frame_origin = urlparse(frame_url).scheme + '://' + urlparse(frame_url).netloc
                                    if script_url == '' or script_url == frame_url: 
                                        continue
                                    else:
                                        try:
                                            ta, tb, tc = extract(script_url)
                                            script_domain = tb + '.' + tc

                                            ta, tb, tc = extract(frame_url)
                                            frame_domain = tb + '.' + tc
                                            
                                            if script_domain == frame_domain:
                                                # ADDED FOR RESUBMISSION
                                                # STATIC FIRST-PARTY SCRIPTS ARE ALWAYS TRUSTED, NO NEED TO GENERATE POLICIES
                                                continue
                                            else:
                                                if script_url.startswith('https://'):
                                                    script_url = script_url[6:]
                                                elif script_url.startswith('http://'):
                                                    script_url = script_url[5:]
                                                config["match"] = script_url
                                        except Exception as e:
                                            if script_url.startswith('https://'):
                                                script_url = script_url[6:]
                                            elif script_url.startswith('http://'):
                                                script_url = script_url[5:]
                                            config["match"] = script_url

                                    url2configs[frame_url].append(config)
                            

                            if rank not in rank2url2configs:
                                rank2url2configs[rank] = dict()
                            for url, configs in list(url2configs.items()):
                                if url not in rank2url2configs[rank]:
                                    rank2url2configs[rank][url] = list()
                                for config in configs:
                                    rank2url2configs[rank][url].append(config)


                            if len(conflict_context2target2info) > 0:
                                for context, target2infos in list(conflict_context2target2info.items()):
                                    for target, infos in list(target2infos.items()):
                                        conflict_context2target2info[context][target] = list(infos)
                                output_file = '%d.conflicts'%(int(rank))
                                output_file = os.path.join(raw_input_dir, output_file)
                                output_file = os.path.join(processed_data_dir, output_file)
                                with open(output_file, 'w') as output_f:
                                    output_f.write(json.dumps(conflict_context2target2info))

                    except OSError as e:
                        pass
                    except Exception as e:
                        try:
                            exc_type, exc_value, exc_traceback = sys.exc_info()
                            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                            print((''.join('!! ' + line for line in lines)))
                            sys.stdout.flush()
                        except Exception:
                            pass

                        pass
                
            except KeyboardInterrupt as e:
                kill_all_processes()
            except Exception as e:
                status = 'Process %-4d task %s/%s raised an exception %s when processing URL [%d].' % (process_index, task_id+1, length, type(e), rank)
                status_queue.put([process_index, status])
                string = '%s\t%s' % (getlocaltime(), status)
                try:
                    print(task_file)
                    print(string)
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                    print((''.join('!! ' + line for line in lines)))
                    sys.stdout.flush()
                except Exception:
                    pass

        
        for rank, url2configs in list(rank2url2configs.items()):
            output_file = str(rank) + '.configs'
            output_file = os.path.join(raw_input_dir, output_file)
            output_file = os.path.join(processed_data_dir, output_file)
            url2domain2ids = dict()
            for url, configs in list(url2configs.items()):
                for config in configs:
                    context_id = config['world_id']
                    script_url = config['match']
                    if script_url.startswith('//'):
                        script_url = 'http:' + script_url 
                        try:
                            ta, tb, tc = extract(script_url)
                            script_domain = tb + '.' + tc
                        except Exception as e:
                            script_domain = script_url
                    else:
                        script_domain = script_url
                    if url not in url2domain2ids:
                        url2domain2ids[url] = dict()
                    if script_domain not in url2domain2ids[url]:
                        url2domain2ids[url][script_domain] = set()
                    url2domain2ids[url][script_domain].add(context_id)
            url2trusted_domains = dict()
            for url, domain2ids in list(url2domain2ids.items()):
                if url not in url2trusted_domains:
                    url2trusted_domains[url] = set()
                for domain, ids in list(domain2ids.items()):
                    if '1' in ids:
                        url2trusted_domains[url].add(domain)

            corrected_url2configs = dict()
            for url, configs in list(url2configs.items()):
                if url not in corrected_url2configs:
                    corrected_url2configs[url] = list()

                for config in configs:
                    context_id =  config['world_id']
                    if context_id != '3':
                        corrected_url2configs[url].append(config)
                        continue
                    script_url = config['match']
                    if script_url.startswith('//'):
                        script_url = 'http:' + script_url 
                        try:
                            ta, tb, tc = extract(script_url)
                            script_domain = tb + '.' + tc
                        except Exception as e:
                            script_domain = script_url
                    else:
                        script_domain = script_url
                    correct_config = config
                    if script_domain in url2trusted_domains[url]: # propagate trust based on domains
                        correct_config['world_id'] = '1'

                    corrected_url2configs[url].append(correct_config)


            if len(corrected_url2configs) > 0:
                with open(output_file, 'w') as output_f:
                    output_f.write(json.dumps(corrected_url2configs))
                print(output_file)

            output_file = str(rank) + '.configs-simple'
            output_file = os.path.join(raw_input_dir, output_file)
            output_file = os.path.join(processed_data_dir, output_file)
            simple_url2configs = dict()
            for url, configs in list(corrected_url2configs.items()):
                if url not in simple_url2configs:
                    simple_url2configs[url] = dict()
                for config in configs:
                    script_url = config['match']
                    if script_url.startswith('//'):
                        script_url = 'http:' + script_url 
                        try:
                            ta, tb, tc = extract(script_url)
                            script_domain = tb + '.' + tc
                        except Exception as e:
                            script_domain = script_url
                    else:
                        script_domain = script_url
                    worldid = config['world_id']
                    if worldid == 'both':
                        if script_url.startswith('https://'):
                            script_url = script_url[6:]
                        elif script_url.startswith('http://'):
                            script_url = script_url[5:]
                        simple_url2configs[url][script_url] = worldid
                    else:
                        simple_url2configs[url][script_domain] = config['world_id']
            if len(simple_url2configs) > 0:
                with open(output_file, 'w') as output_f:
                    output_f.write(json.dumps(simple_url2configs))
                print(output_file)

    except OSError as e:
        pass
    except Exception as e:
        status = 'Process %-4d task %s/%s raised an exception %s.' % (process_index, task_id+1, length, type(e))
        status_queue.put([process_index, status])
        string = '%s\t%s' % (getlocaltime(), status)
        try:
            print(string)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print((''.join('!! ' + line for line in lines)))
            sys.stdout.flush()
        except Exception:
            pass

    status = 'Process %-4d task %s/%s PID [%d] completed.' % (process_index, task_id+1, length, current_pid)
    status_queue.put([process_index, status])




def main(argv):
    global raw_data_dir, processed_data_dir, num_instances, parent_pid, process_list, log_f, extract,domain2revdomains
    signal.signal(signal.SIGTERM, signal_term_handler)
    parent_pid = os.getpid()
    try:
        opts, args = getopt.getopt(argv, 'hu:d:i:n:p:s:e:t:', ['help', 'user_dir=', 'exp_dir=', 'num=', 'process=', 'start=', 'end=', 'type='])
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
        elif opt in ('-h', '--help'):
            usage()
            sys.exit(0)

    if user_dir is None:
        usage()
        sys.exit(0)


    extract = tldextract.TLDExtract(include_psl_private_domains=True)
    
    input_file = 'top-1m.csv'
    domain2revdomains = dict()
    with open('domain2revlist.json', 'r') as input_f:
        domain2revdomains = json.loads(input_f.read())

    raw_data_dir = exp_dir
    processed_data_dir = os.path.join(exp_dir, 'domain-level-policies')
    if not os.path.isdir(processed_data_dir):
        try:
            os.mkdir(processed_data_dir)
        except Exception as e:
            print(e)


    log_file = 'convert_asg_logs.log'
    log_file = os.path.join(exp_dir, log_file)
    log_f = open(log_file, mode='w')

    current_time = getlocaltime()
    status = "PARENT SCRIPT STARTED! PARENT PID=[%d]" % parent_pid
    string = '%s\t%s\n' % (current_time, status)
    log_f.write(string)
    string = "%s\tProcess started, argv=%s\n" % (current_time, argv)
    log_f.write(string)


    completed_list = set()
    completion_reg = re.compile('Process [0-9\s]+task ([0-9]+)/[0-9]+ PID \[\d+\] completed.')
    with codecs.open(log_file, encoding='utf-8', mode='r') as input_f:
        for line in input_f:
            m = re.search(completion_reg, line)
            if m:
                task = int(m.group(1)) - 1
                completed_list.add(task)
    completed_list = set()


    try:
        os.chdir(exp_dir)
    except OSError as e:
        print(e)
        sys.exit(1)


    tasks = [i for i in range(num_instances-1, -1, -1)]
    try:
        length = len(tasks)
        status_queue = Queue()
        final_status_set = set()
        process_num = 0
        process2status = dict()
        running_processes = set()
        process2index = dict()
        index2task = dict()
        round_num = 0
        process_list = list()
        killed_process_list = list()
        alive_check_timeout = 10
        alive_count = 0

        while len(tasks) > 0 or len(running_processes) > 0:
            current_time = getlocaltime()
            num_alive_processes = sum(1 for process in process_list if process.is_alive())
            status = '[%d] processes are still alive, [%d] are running ...' % (num_alive_processes, len(running_processes))
            string = '%s\t%s\n' % (current_time, status)
            print(string)
            sys.stdout.flush()

            while len(running_processes) < maximum_process_num and len(tasks) > 0:
                group = tasks.pop()
                task = group
                if task in completed_list:
                    continue
                user_dir_group = '%s_%d' % (user_dir, group)
                process_index = process_num
                #task_list = task_queue[task]
                try:
                    process_list.append(Task(target=measure, args=(user_dir_group, task, length, start, end, status_queue, process_index)))
                    process = process_list[-1]
                    process.start()
                except OSError as e:
                    tasks.append(group)
                    time.sleep(5)
                    continue
                process_num += 1
                running_processes.add(process_list[-1])
                process2index[process_list[-1]] = process_index
                index2task[process_index] = task

                current_time = getlocaltime()
                process_status = 'Process %-4d task %d/%d created. PID=%d ...' % (process_index, task+1, length, process.pid)
                string = '%s\t%s' % (current_time, process_status)
                print(string)
                sys.stdout.flush()
                if process_num % 32 == 0:
                    break

            flag = False
            while any(process.is_alive() for process in process_list):
                time.sleep(1)
                current_time = getlocaltime()
                alive_count += 1
                num_alive_processes = sum(1 for process in process_list if process.is_alive())

                while not status_queue.empty():
                    process_index, process_status = status_queue.get()
                    string = '%s\t%s\n' % (current_time, process_status)
                    log_f.write(string)
                    if 'completed' in process_status:
                        flag = True
                        if process_status not in final_status_set:
                            final_status_set.add(process_status)

                if alive_count % alive_check_timeout == 0:
                    status = '[%d] processes are still alive ...' % (num_alive_processes)
                    string = '%s\t%s\n' % (current_time, status)
                    print(string)
                    sys.stdout.flush()

                    # We need to get a list. Otherwise, we will receive an exception: RuntimeError: Set changed size during iteration
                    for process in list(running_processes):
                        process_index = process2index[process]
                        group = index2task[process_index]

                        if not process.is_alive():
                            flag = True
                            process_status = 'Process %-4d task %d/%d is no longer alive...' % (process_index, group+1, length)
                        else:
                            process_status = 'Process %-4d task %d/%d is still alive...' % (process_index, group+1, length)
                        string = '%s\t%s\n' % (current_time, process_status)
                        log_f.write(string)

                if flag == True or (num_alive_processes < maximum_process_num and (len(tasks) > 0 or alive_count % alive_check_timeout == 0)):
                    break
            for process in process_list:
                if not process.is_alive():
                    if process in running_processes:
                        running_processes.remove(process)


    except (KeyboardInterrupt, Exception) as e:
        current_time = getlocaltime()
        status = "PARENT SCRIPT exception %s" % type(e)
        string = '%s\t%s\n' % (current_time, status)
        log_f.write(string)
        if not isinstance(e, KeyboardInterrupt):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print((type(e), "PARENT"))
            print((''.join('!! ' + line for line in lines)))
            status = ''.join('!! ' + line for line in lines)
            string = '%s\t%s\n' % (current_time, status)
            log_f.write(string)

        kill_all_processes()

    while not status_queue.empty():
        process_index, process_status = status_queue.get()
        string = '%s\t%s\n' % (current_time, process_status)
        log_f.write(string)

    for process in process_list:
        try:
            process.join()
        except Exception:
            pass

    gone, alive = kill_child_processes(parent_pid = parent_pid)

    timeout = 10
    while timeout:
        time.sleep(1)
        timeout -= 1
        if not mp.active_children():
            break

    current_time = getlocaltime()
    status = "PARENT SCRIPT COMPLETED! PARENT PID=[%d]" % parent_pid
    string = '%s\t%s\n' % (current_time, status)
    log_f.write(string)
    log_f.close()




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

if __name__ == '__main__':
    main(sys.argv[1:])

