# Used to run chromium browser using selenium
# python log_access.py -u <user_dir> -d <data_dir> -s xxx -e yyy -i <input_file> -n <num_instances> -p <num_processes>
# xxx: starting rank
# yyy: end rank
# <input_file>: a file containing the domain name of websites, each line in format: <rank,domain_name>
# REMEMBER TO PUT THIS FILE UNDER THE SAME FOLDER WITH A profile-template FOLDER !!

import random, time, os, shutil, re, codecs, sys, json, traceback, getopt, http.client, subprocess, tldextract, importlib
import signal, psutil
import numpy as np
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import *
from selenium.webdriver.common.keys import Keys
from multiprocessing import Process as Task, Queue, Lock
import multiprocessing as mp
from subprocess import call, PIPE, STDOUT
from urllib.parse import urlparse
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# This script do not need to destroy browser process between navigations
# This script can not capture browser event traces

importlib.reload(sys)
up = r'../'

ROOT = os.path.dirname(os.path.realpath(__file__))
PROFILE_TEMPLATE_DIR = os.path.join(ROOT, 'profile-template')
ISOLATE_CHROME = os.path.join(ROOT, "../binaries/isolation/chrome") # or change this to your local path of the js isolation browser
CLEAN_CHROME = os.path.join(ROOT, "../binaries/clean/chrome") # or change this to your local path of the clean browser
#ISOLATE_CHROME = os.path.join(ROOT, "../chromium/src/out/isolation/chrome") # use this when build from source code
#CLEAN_CHROME = os.path.join(ROOT, "../chromium/src/out/clean/chrome") # use this when build from source code


class FunctionTimeoutException(Exception):
    pass

class NavigationStuckException(Exception):
    pass

class TooManyTasksDead(Exception):
    pass

def restart_all_tasks(log_f):
    #status = 'Restarting [GDM]...'
    #current_time = getlocaltime()
    #string = '%s\t%s\n' % (current_time, status)
    #print(string)
    #log_f.write(string)

    #cmd = ['eudo', 'service', 'gdm', 'restart']
    #process = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    #out, err = process.communicate()

    time.sleep(1)

    status = 'Restarting [PARENT SCRIPT]...'
    current_time = getlocaltime()
    string = '%s\t%s\n' % (current_time, status)
    print(string)
    log_f.write(string)
    log_f.close()
    argv = sys.argv + ['&']

    #os.execl('/usr/bin/nohup', '/usr/bin/python', *argv)
    os.execl('/usr/bin/python', '/usr/bin/python', *sys.argv)

# Garbage collection of terminated chrome processes
def gc_chrome_tmp_files(force=False):
    global log_f
    tmp_dir = '/tmp'
    num = 0
    for p in os.listdir(tmp_dir):
        path = os.path.join(tmp_dir, p)
        if os.path.isfile(path) and p.startswith('domac-browser'):
            flag = force
            if not force:
                try:
                    pid = int(p.split('-')[-1])
                except ValueError:
                    continue
                try:
                    os.kill(pid, 0)
                except OSError:
                    # The pid is not running
                    flag = True
            if flag:
                try:
                    #print("Removing [%s]" % path)
                    os.remove(path)
                    num += 1
                except OSError as e:
                    pass
    status = 'GC [%d] files.' % (num)
    current_time = getlocaltime()
    string = '%s\t%s\n' % (current_time, status)
    log_f.write(string)

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

def kill_processes_by_name(name):
    for process in psutil.process_iter():
        try:
            cmdline = ' '.join(process.cmdline())
            if name not in cmdline:
                continue
            #print(cmdline)
            #sys.stdout.flush()
            #pid = process.pid
            kill_child_processes(parent = process)
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            pass

def create_browser(proxy_port, log_pass, window_size="1024,768", binary_path=None, user_dir=None, env=None, ext=None, log_file=None, headless=None, config_file=None, policy_mode=None):
    if config_file:
        os.environ["CONFIG_FILE"] = config_file
    else:
        try:
            del os.environ["CONFIG_FILE"]
        except KeyError:
            pass

    if policy_mode:
        os.environ["POLICY_MODE"] = policy_mode
    else:
        try:
            del os.environ["POLICY_MODE"]
        except KeyError:
            pass
    
    if log_pass:
        os.environ["FALLBACK_CONTEXT"] = str(log_pass)
    else:
        try:
            del os.environ["FALLBACK_CONTEXT"]
        except KeyError:
            pass

    caps = DesiredCapabilities.CHROME
    caps["loggingPrefs"] = {"performance": "ALL"}

    options = Options()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')    
    options.add_argument('--disable-component-extensions-with-background-pages')
    options.add_argument("--disable-notifications")
    options.add_argument("--disk-cache-dir=/dev/null")
    options.add_argument("--disk-cache-size=1")
    options.add_argument("--media-cache-size=1")
    options.add_argument("--ignore-certificate-errors")

    chromedriver_port = 10000 + os.getpid()

    if binary_path:
        options.binary_location= binary_path
    if headless:
        options.add_argument('--headless')
    if user_dir:
        options.add_argument('--user-data-dir='+user_dir)

    try:
        if log_file:
            browser = webdriver.Chrome(chrome_options=options, desired_capabilities=caps, service_args=['--verbose', '--log-path=%s' % log_file]) 
        else:
            browser = webdriver.Chrome(chrome_options=options, desired_capabilities=caps) 
    except WebDriverException as e:
        print(('Failed to create browser for PID [%d]!!!' % (os.getpid())))
        try:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print((''.join('!! ' + line for line in lines)))
            sys.stdout.flush()
        except Exception:
            pass
        pass

        return None
    browser.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
    browser.execute_cdp_cmd("Network.clearBrowserCache", {})

    return browser

def close_browser(browser):
    browser.quit()

def wait_find_element_by_id(driver, _id, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, _id)))
    except TimeoutException as e:
        pass
    return result

def wait_find_element_by_tag_name(driver, name, timeout=5):

    result = None
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, name)))
    except TimeoutException as e:
        pass
    return result

def wait_find_elements_by_tag_name(driver, name, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_all_element_located((By.TAG_NAME, name)))
    except TimeoutException as e:
        pass
    return result

def wait_find_element_by_class_name(driver, name, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, name)))
    except TimeoutException as e:
        pass
    return result

def wait_find_elements_by_class_name(driver, name, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_all_element_located((By.CLASS_NAME, name)))
    except TimeoutException as e:
        pass
    return result

def wait_find_element_by_xpath(driver, xpath, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))
    except TimeoutException as e:
        pass
    return result

def wait_find_elements_by_xpath(driver, xpath, timeout=5):
    result = None
    try:
        result = WebDriverWait(driver, timeout).until(EC.presence_of_all_element_located((By.XPATH, xpath)))
    except TimeoutException as e:
        pass
    return result

def get_date_string(t):
    return time.strftime("%Y%m%d%H%M%S", t)

def get_time(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", t)

def prepare_profile(user_dir, remove_only=False):
    try:
        shutil.rmtree(user_dir)
    except OSError as e:
        pass
    if not remove_only:
        shutil.copytree(PROFILE_TEMPLATE_DIR, user_dir)

def get_max_size(driver):
    global get_max_size_script
    return driver.execute_script(get_max_size_script)

def fetch_doc_log(driver):
    global fetch_doc_log_script
    return driver.execute_script(fetch_doc_log_script)

def fire_events(driver):
    global fire_events_script
    return driver.execute_script(fire_events_script)
    #return driver.execute_async_script(fire_events_script)


def fetch_frame_logs(driver):
    global fetch_asg_logs_script
    return driver.execute_script(fetch_asg_logs_script)
	
def getlocaltime():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def save_result_files(logs_dir, rank, user_dir, first_party_domain):
    global chrome_newtab_url, about_blank_url, chrome_extension_prefix, chrome_extension_suffix, last_rank, last_logs_dir, extract

    last_rank = rank
    last_logs_dir = logs_dir

    subframe_count = 0
    subaccess_count = 0
    subscript_count = 0
    subid2url_count = 0
    subid2parent_count = 0
    sub3p_count = 0
    children_tmp1 = get_child_processes(os.getpid())
    dst_folder_tmp = logs_dir 
    main_frame_pid = -1
    main_frame_filename = None
   
    debug_log_dir = os.path.join(os.getcwd(), user_dir)
    for f in os.listdir(debug_log_dir):
        if 'chrome_debug.log' == f:
            old_f = os.path.join(debug_log_dir, f)
            dst_logs_filename = 'exception_' + str(last_rank) + '.log'
            dst_logs_filename = os.path.join(last_logs_dir, dst_logs_filename)
            try:
                shutil.move(old_f, dst_logs_filename)
            except IOError as e:
                pass
            except OSError as e:
                pass

    found_mv_files = False
    for child in children_tmp1:
        try:
            child_pid = child.pid
        except Exception as e:
            child_pid = child
        mv_filename = str(child_pid) + '.frame'
        access_filename = str(child_pid) + '.access'
        id2url_filename = str(child_pid) + '.id2url'
        id2parent_filename = str(child_pid) + '.id2parentid'
        three_filename = str(child_pid) + '.3p'
        is_main_frame_file = False
        script_file_list = os.listdir(os.getcwd())
        script_file_list = [f_ for f_ in script_file_list if f_.split('.')[-1] == 'script' and int(f_.split('.')[0]) == child_pid]
        new_script_file_list = []
        try:
            f = open(mv_filename, 'r')
        except Exception as e:
            access_new_filename = str(rank) + '.' + 'sub.' + str(subaccess_count) + '.access'
            access_new_filename = os.path.join(dst_folder_tmp, access_new_filename)

            try:
                shutil.move(access_filename, access_new_filename)
                found_mv_files = True
                subaccess_count += 1
            except OSError as e:
                pass
            except IOError:
                pass
            id2url_new_filename = str(rank) + '.' + 'sub.' + str(subid2url_count) + '.id2url'
            id2url_new_filename = os.path.join(dst_folder_tmp, id2url_new_filename)

            try:
                shutil.move(id2url_filename, id2url_new_filename)
                found_mv_files = True
                subid2url_count += 1
            except OSError as e:
                pass
            except IOError:
                pass
            id2parentid_new_filename = str(rank) + '.' + 'sub.' + str(subid2parent_count) + '.id2parentid'
            id2parentid_new_filename = os.path.join(dst_folder_tmp, id2parentid_new_filename)

            try:
                shutil.move(id2parent_filename, id2parentid_new_filename)
                found_mv_files = True
                subid2parent_count += 1
            except OSError as e:
                pass
            except IOError:
                pass

            three_new_filename = str(rank) + '.' + 'sub.' + str(sub3p_count) + '.3p'
            three_new_filename = os.path.join(dst_folder_tmp, three_new_filename)

            try:
                shutil.move(three_filename, three_new_filename)
                found_mv_files = True
                sub3p_count += 1
            except OSError as e:
                pass
            except IOError:
                pass
            continue

        try:
            lines = f.read().split('\n')[:-1]
            for line in lines:
                type_ = line.split(' ')[0]
                url_ = line.split(' ')[1]
                if(type_ == '[main]' and chrome_newtab_url not in url_ and about_blank_url not in url_):
                    if not (url_.startswith(chrome_extension_prefix) and url_.endswith(chrome_extension_suffix)):
                        i = 0
                        while True:
                            new_file = "%d.main.%d" %(rank, i)
                            mv_new_filename = new_file + ".frame"
                            mv_new_filename = os.path.join(dst_folder_tmp, mv_new_filename)
                            if not os.path.isfile(mv_new_filename):
                                access_new_filename = new_file + ".access"
                                access_new_filename = os.path.join(dst_folder_tmp, access_new_filename)
                                id2url_new_filename = new_file + ".id2url"
                                id2url_new_filename = os.path.join(dst_folder_tmp, id2url_new_filename)
                                id2parent_new_filename = new_file + ".id2parentid"
                                id2parent_new_filename = os.path.join(dst_folder_tmp, id2parent_new_filename)
                                three_new_filename = new_file + '.3p'
                                three_new_filename = os.path.join(dst_folder_tmp, three_new_filename)


                                for f_ in script_file_list:
                                    script_id = f_.split('.')[1]
                                    new_filename = new_file + '.' + script_id + '.script'
                                    new_filename = os.path.join(dst_folder_tmp, new_filename)
                                    new_script_file_list.append((f_, new_filename))
                                break
                            i += 1
                        is_main_frame_file = True
                        main_frame_pid = child_pid
                        main_frame_filename = mv_new_filename
                        break
            f.close()
            if not is_main_frame_file:
                mv_new_filename = str(rank) + '.' + 'sub.' + str(subframe_count) + '.frame'
                mv_new_filename = os.path.join(dst_folder_tmp, mv_new_filename)
                access_new_filename = str(rank) + '.' + 'sub.' + str(subaccess_count) + '.access'
                access_new_filename = os.path.join(dst_folder_tmp, access_new_filename)
                id2url_new_filename = str(rank) + '.' + 'sub.' + str(subid2url_count) + '.id2url'
                id2url_new_filename = os.path.join(dst_folder_tmp, id2url_new_filename)
                id2parent_new_filename = str(rank) + '.' + 'sub.' + str(subid2parent_count) + '.id2parentid'
                id2parent_new_filename = os.path.join(dst_folder_tmp, id2parent_new_filename)
                three_new_filename = str(rank) + '.' + 'sub.' + str(sub3p_count) + '.3p'
                three_new_filename = os.path.join(dst_folder_tmp, three_new_filename)



                for f in script_file_list:
                    script_id = f.split('.')[1]
                    new_filename = str(rank) + '.' + 'sub.' + str(subscript_count) + '.' + script_id + '.script'
                    new_filename = os.path.join(dst_folder_tmp, new_filename)
                    new_script_file_list.append((f, new_filename))
                subframe_count += 1
                subaccess_count += 1
                subid2url_count += 1
                subid2parent_count += 1
                subscript_count += 1
                sub3p_count += 1

        except OSError as e:
            pass

        try:
            shutil.move(mv_filename, mv_new_filename)
            found_mv_files = True
        except OSError as e:
            pass
        except IOError:
            pass
        
        try:
            shutil.move(id2parent_filename, id2parent_new_filename)
            found_mv_files = True
        except OSError as e:
            pass
        except IOError:
            pass

        try:
            shutil.move(access_filename, access_new_filename)
            found_mv_files = True
        except OSError as e:
            pass
        except IOError:
            pass
        try:
            shutil.move(id2url_filename, id2url_new_filename)
            found_mv_files = True
        except OSError as e:
            pass
        except IOError as e:
            pass

        try:
            shutil.move(three_filename, three_new_filename)
            found_mv_files = True
        except OSError as e:
            pass
        except IOError:
            pass

        for f in new_script_file_list:
            try: 
                shutil.move(f[0], f[1])
            except OSError as e:
                continue
            except IOError as e:
                continue

    if not found_mv_files:
        should_mv_pids = list()
        old_files = os.listdir(os.getcwd())
        frame_files = [f for f in old_files if f.split('.')[-1] == 'frame']
        for frame_file in frame_files:
            with open(frame_file, 'r') as input_f:
                for line in input_f:
                    if line.startswith('[main]'):
                        frame_url = line.split('\n')[0].split()[1]
                        try:
                            frame_parse = urlparse(frame_url)
                            frame_host = frame_parse.hostname
                            ext = extract(frame_host)
                            frame_domain = ext.domain
                            
                            if frame_domain == first_party_domain:
                                should_mv_pids.append(frame_file.split('.')[0])
                        except Exception as e:
                            continue
        pid2count = dict()
        count = 0
        for old_file in old_files:
            old_pid = old_file.split('.')[0]
            if old_pid in should_mv_pids:
                if old_pid not in pid2count:
                    pid_count = count
                    pid2count[old_pid] = count
                    count += 1
                else:
                    pid_count = pid2count[old_pid]
                new_file = str(rank) + '.main.%d.'%(pid_count) + '.'.join(old_f.split('.')[1:])
                mv_new_filename = os.path.join(dst_folder_tmp, new_f)
                try:
                    shutil.move(old_f, mv_new_filename)
                except OSError as e:
                    print(e)
                    pass
                except IOError:
                    print('ioerror')
                    pass
    return main_frame_pid




def measure(user_dir, task_id, length, start, end, status_queue, process_index):
    global rank2domain, access_control, find_sub_pages_script, num_instances, log_dir, script_dir, logs_dir, browser, chrome_newtab_url, about_blank_url, chrome_extension_prefix, chrome_extension_suffix, rank, config_dir, log_pass, extract, p_mode

    current_pid = os.getpid()
    random.seed(time.time())

    chrome_newtab_url = 'https://www.google.com/_/chrome/newtab'
    about_blank_url = 'about:blank'
    chrome_extension_prefix = 'chrome-extension://'
    chrome_extension_suffix = 'generated_background_page.html'
    try:
        status = 'Process %-4d task %d/%d PID [%d] starting ...' % (process_index, task_id+1, length, current_pid)
        status_queue.put([process_index, status])
    except Exception as e:
        pass

    try:
        os.mkdir(user_dir)
    except OSError as e:
        pass
    os.chdir(user_dir)

    try:
        filenames = os.listdir(log_dir)
    except OSError as e:
        return
    logs_dir = user_dir+'_logs'
    logs_dir = os.path.join(log_dir, logs_dir)
    try:
        os.mkdir(logs_dir)
    except OSError as e:
        pass
    log_file = '%s.log' % (user_dir)
    log_file = os.path.join(log_dir, log_file)
    webdriver_log = 'webdriver_%s.log' % (user_dir)
    processed_list = list()
    failed_list = list()
    log_f = None
    try:
        log_f = open(log_file, 'r')
        for line in log_f:
            data = line[:-1].split('\t')
            rank = int(data[1])
            status = data[3]
            if status == 'main':
                url = data[2]
                if not url.startswith(about_blank_url):
                    processed_list.append(rank)
            elif status == 'failed':
                url = data[2]
                if not url.startswith(about_blank_url):
                    failed_list.append(rank)
        log_f.close()
    except IOError as e:
        pass

    filenames = [f for f in filenames if f.endswith('.json') and f.startswith(user_dir)]
    rank2files = dict()
    files = list()
    try:
        files += os.listdir(logs_dir)
    except OSError as e:
        return
    valid_suffixs = ['mem', 'time', 'mem_isolate', 'time_isolate']

    for f in files:
        split_list = f.split('.')
        rank = split_list[0]
        try:
            rank = int(rank)
        except ValueError:
            continue
        if rank not in rank2files:
            rank2files[rank] = list()
        suffix = ""
        if len(split_list) == 4:
            suffix = split_list[1] + split_list[3]
        elif len(split_list) == 2:
            suffix = split_list[1]
        if suffix in valid_suffixs:
            rank2files[rank].append(suffix)
    completed_list = [rank for rank, suffix_list in list(rank2files.items()) if len(suffix_list) >= 4]

    del rank2files

    browser = None
    display = None
    chromedriver_process = None
    count = 0
    task_list = set(processed_list + failed_list)
    task_list = set([rank for rank in task_list if rank >= start and rank <= end])
    processed_list = set(completed_list)
    processed_list = set([rank for rank in processed_list if rank >= start and rank <= end])
    processed_list = set()

    rank2fail_num = dict()
    last_rank = None
    last_logs_dir = None
    while True:
        try:
            last_url = None
            for rank, domain in sorted(rank2domain.items()):
                if rank > end:
                    break
       
                if rank % num_instances != task_id or rank in processed_list or rank < start:
                    continue
                    if rank in processed_list:
                        print(('finished', rank))
                
                if rank in rank2fail_num and rank2fail_num[rank] >= 1:
                    continue
                task_list.add(rank)
                
                debug_log_file = 'chrome_debug.log'
                debug_log_file = os.path.join(os.path.join(os.getcwd(), user_dir), debug_log_file)
                debug_log_file = os.path.join(os.getcwd(), debug_log_file)
                try:
                    if os.path.isfile(debug_log_file) and last_rank is not None and last_logs_dir is not None:
                        dst_logs_filename = 'exception_' + str(last_rank) + '.log'
                        dst_logs_filename = os.path.join(last_logs_dir, dst_logs_filename)
                        try:
                            shutil.move(debug_log_file, dst_logs_filename)
                        except IOError as e:
                            pass
                        except OSError as e:
                            pass
                        last_rank = None
                        last_logs_dir = None
                except Exception as e:
                    pass  
               
                prev_file_list = os.listdir(os.getcwd())
                for f in prev_file_list:
                    try:
                        os.remove(f)
                    except Exception as e:
                        pass
 

                config_input_dir = os.path.join(config_dir, user_dir+'_logs_collect')
                config_f = os.listdir(config_input_dir)
                config_f = [f for f in config_f if f.split('.')[0]==str(rank) and f.endswith('.configs-simple')]
                if len(config_f) == 0:
                    #print('no config file found')
                    processed_list.add(rank)
                    continue
                config_f = config_f[0]
                config_f = os.path.join(config_input_dir, config_f)

                CHROME_BINARY = None
                if log_pass == 0:
                    CHROME_BINARY = CLEAN_CHROME
                else: # must be 1 or 3
                    CHROME_BINARY = ISOLATE_CHROME

                # Second, open browser using selenium
                # Open a new browser for each visit
                if browser is None or count % 1 == 0: # reopen the browser for each page
                    if browser is not None:
                        try:
                            close_browser(browser)
                        except Exception as e:
                            pass
                        except KeyboardInterrupt as e:
                            raise e                    
                    gone, alive = kill_child_processes(parent_pid = current_pid)
                    process_name = 'user-data-dir=%s' % (user_dir)
                    kill_processes_by_name(process_name)
                    process_name = 'log-path=webdriver_%s.log' % (user_dir)
                    kill_processes_by_name(process_name)

                    i = 0
                    while True:
                        prepare_profile(user_dir=user_dir)
                        # register the signal function handler
                        signal.signal(signal.SIGALRM, function_timeout_handler)
                        # define a timeout for the function
                        timeout = min(max(i, 15), 30)
                        #timeout = 100
                        signal.alarm(timeout)
                        # run the function
                        try:
                            proxy_port = 8000 + task_id
                            if log_pass != 0:
                                browser = create_browser(proxy_port, log_pass, binary_path=CHROME_BINARY, user_dir = user_dir, log_file=webdriver_log, headless=False, config_file=config_f, policy_mode=p_mode)
                            else:
                                browser = create_browser(proxy_port, log_pass, binary_path=CHROME_BINARY, user_dir = user_dir, log_file=webdriver_log, headless=False, config_file=None, policy_mode=p_mode)

                            if browser is not None:
                                chromedriver_process = browser.service.process
                        except (FunctionTimeoutException, OSError) as e:
                            print(e)
                            status = 'process %-4d task %d/%d browser creation failed!!!' % (process_index, task_id+1, length)
                            status_queue.put([process_index, status])
                            string = '%s\t%s' % (getlocaltime(), status)
                            browser = None
                        except (KeyboardInterrupt, Exception) as e:
                            signal.alarm(0)
                            raise e
                        # cancel the timer if the function returned before timeout
                        signal.alarm(0)
                        if browser is not None:
                            time.sleep(1)
                            break

                        gone, alive = kill_child_processes(parent_pid = current_pid)
                        process_name = 'user-data-dir=%s' % (user_dir)
                        kill_processes_by_name(process_name)
                        process_name = 'log-path=webdriver_%s.log' % (user_dir)
                        kill_processes_by_name(process_name)

                        i += 1
                        low = 1
                        high = 5
                        sleep_interval = random.randint(low, high)
                        time.sleep(sleep_interval)

            
                time.sleep(2)

                # register the signal function handler
                signal.signal(signal.SIGALRM, function_timeout_handler)
                # define a timeout for the function
                timeout = 160
                signal.alarm(timeout)
                start_time = time.time()
                # run the function
                
                if input_type == 'url':
                    url = domain
                else:
                    url = "http://www."+domain

                try:
                    browser.set_page_load_timeout(120)
                    #browser.manage().timeouts().pageLoadTimeout(60, TimeUnit.SECONDS)
                    #browser.implicitly_wait(60)
                    log_f = open(log_file, 'a')
                    status = 'visit'
                    l = '%s\t%d\t%s\t%s\n' % (getlocaltime(), rank, url, status)
                    log_f.write(l)
                    log_f.close()

                    load_start = time.time()
                    load_end = None
                    browser.get(url)
                    #status = 'process %-4d task %d/%d %s loaded in %f seconds' % (process_index, task_id+1, length, url, time.time() - start_time)
                    #print(status)
                    #sys.stdout.flush()
                except TimeoutException as e:
                    #print('timeout for 1 time...')
                    #status = 'process %-4d task %d/%d %s timed out in %f seconds' % (process_index, task_id+1, length, url, time.time() - start_time)
                    #print(status)
                    #sys.stdout.flush()
                    pass
                except UnexpectedAlertPresentException as e:
                    alert1 = browser.switch_to_alert()
                    #browser.switch_to_window(current_handle)
                    #browser.switch_to_window(current_handle)
                    alert1.dismiss() 

                try:
                    # wait for at most another 20 seconds if the get(url) call above has timed out
                    WebDriverWait(browser, 20).until(lambda d: d.execute_script('return document.readyState;') == 'complete')
                    #print('after 2nd wait', time.time()-load_start)
                    #WebDriverWait(browser, 20).until(EC.presence_of_element_located((By.XPATH, "/html/body")))
                    #status = 'process %-4d task %d/%d %s waited in %f seconds' % (process_index, task_id+1, length, url, time.time() - start_time)
                    #print(status)
                    #sys.stdout.flush()
                except TimeoutException as e:
                    #print('timeout for 2 time...', time.time()-load_start)
                    # this is the second TimeoutException, we need to abort the page load
                    #status = 'process %-4d task %d/%d %s timed out again in %f seconds' % (process_index, task_id+1, length, url, time.time() - start_time)
                    #print(status)
                    #sys.stdout.flush()
                    # we wait for at most another 5 seconds to stop the page load
                    browser.set_page_load_timeout(5)
                    try:
                        webdriver.ActionChains(browser).send_keys(Keys.ESCAPE).perform()
                    except TimeoutException as e:
                        # this is the third TimeoutException. try to abort the page load one more time
                        # if we cannot stop it in another 5 seconds, a TimeoutException will be caught finally
                        #print('timeout for 3 time...')
                        browser.execute_script("window.stop();") # we have to use javsscript to stop page loading
                except UnexpectedAlertPresentException as e:
                    alert1 = browser.switch_to_alert()
                    #browser.switch_to_window(current_handle)
                    alert1.dismiss()
                except Exception as e:
                    pass


                # we wait for at most 1 second for reading the current_url
                browser.set_page_load_timeout(1)
                current_url = None
                try:
                    current_url = browser.current_url
                except TimeoutException as e:
                    #print('timeout for 3 time, aborting...')
                    # we need to abort the page load
                    try:
                        browser.set_page_load_timeout(5)
                        webdriver.ActionChains(browser).send_keys(Keys.ESCAPE).perform()
                        current_url = browser.current_url
                    except TimeoutException as e:
                        # this is the second TimeoutException. try to abort the page load one more time
                        # if we cannot stop it in another 5 seconds, a TimeoutException will be caught finally
                        browser.execute_script("window.stop();") # we have to use javsscript to stop page loading
                if current_url:
                    url = current_url
                if url == last_url or url.startswith(chrome_newtab_url) or url.startswith(about_blank_url):
                    raise NavigationStuckException("url is identical with url of last navigation!")

                

                load_end = time.time()
                # we wait for at most 20 seconds for each sychronous script execution
                browser.set_page_load_timeout(20)

                # do not comment the following when measuring compatibility
                #'''
                browser.execute_script("window.scrollTo(0, 0.2*document.body.scrollHeight)")
                time.sleep(1)
                browser.execute_script("window.scrollTo(0, 0.4*document.body.scrollHeight)")
                time.sleep(1)
                browser.execute_script("window.scrollTo(0, 0.6*document.body.scrollHeight)")
                time.sleep(1)
                browser.execute_script("window.scrollTo(0, 0.8*document.body.scrollHeight)")
                time.sleep(1)
                browser.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                time.sleep(10)
                #'''

                if log_pass != 0:
                    proxy_dir = logs_dir + '_proxy'
                    try:
                        os.mkdir(proxy_dir)
                    except OSError as e:
                        pass
                    main_frame_pid = save_result_files(proxy_dir, rank, user_dir, url)
                else:
                    main_frame_pid = save_result_files(logs_dir, rank, user_dir, url)



                navigationStart = browser.execute_script("return window.performance.timing.navigationStart")
                responseStart = browser.execute_script("return window.performance.timing.responseStart")
                loadEventEnd = browser.execute_script("return window.performance.timing.loadEventEnd")
                domComplete = browser.execute_script("return window.performance.timing.domComplete")
                page_load_time = {'navi-load': loadEventEnd-navigationStart, 'navi-dom': domComplete-navigationStart, 'response-load': loadEventEnd-responseStart, 'response-dom': domComplete-responseStart}
                page_load_time = json.dumps(page_load_time)


                output_dir = user_dir + '_logs'
                output_dir = os.path.join(log_dir, output_dir)
                
                time_log_file = str(rank) + '.time'
                if log_pass != 0:
                    time_log_file += '_isolate'
                time_log_file = os.path.join(output_dir, time_log_file)
                with open(time_log_file, 'w') as output_f:
                    output_f.write(str(page_load_time))
                print((time_log_file, page_load_time))
               
                
                
                mem_script_path = script_dir + '/memory.py' #os.path.join(script_dir, logs_dir)
                memory_consumption = -1
                if main_frame_pid != -1:
                    try:
                        memory_consumption = subprocess.check_output(['sudo','python', mem_script_path, str(main_frame_pid)])
                    except Exception as e:
                        pass
                mem_log_file = str(rank) + '.mem'
                if log_pass != 0:
                    mem_log_file += '_isolate'
                mem_log_file = os.path.join(output_dir, mem_log_file)
                with open(mem_log_file, 'w') as output_f:
                    output_f.write(str(memory_consumption))
                print((mem_log_file, memory_consumption))


                gone, alive = kill_child_processes(parent_pid = current_pid)
                process_name = 'user-data-dir=%s' % (user_dir)
                kill_processes_by_name(process_name)
                process_name = 'proxy_port=%d'%(8000+task_id)
                kill_processes_by_name(process_name)
                if log_pass != 0:
                    process_name = 'set config=%s'%(config_f)
                else:
                    process_name = 'mitmdump -p %d'%(8000+task_id)
                kill_processes_by_name(process_name)

                log_f = open(log_file, 'a')
                status = 'main'
                l = '%s\t%d\t%s\t%s\n' % (getlocaltime(), rank, url, status)
                log_f.write(l)
                log_f.close()

                last_url = url

                status = 'process %-4d task %d/%d url [%d] loaded.' % (process_index, task_id+1, length, rank)
                status_queue.put([process_index, status])
                #break # WE USE IT FOR ONLY 1 PASS
                processed_list.add(rank)


                debug_log_file = 'chrome_debug.log'
                debug_log_file = os.path.join(os.path.join(os.getcwd(), user_dir), debug_log_file)
                debug_log_file = os.path.join(os.getcwd(), debug_log_file)
                try:
                    if os.path.isfile(debug_log_file) and last_rank is not None and last_logs_dir is not None:
                        dst_logs_filename = 'exception_' + str(last_rank) + '.log'
                        dst_logs_filename = os.path.join(last_logs_dir, dst_logs_filename)
                        try:
                            shutil.move(debug_log_file, dst_logs_filename)
                        except IOError as e:
                            pass
                        except OSError as e:
                            pass
                        last_rank = None
                        last_logs_dir = None
                except Exception as e:
                    pass   

                # cancel the timer if the function returned before timeout
                signal.alarm(0)

            remaining_tasks = task_list - processed_list
            if len(remaining_tasks) == 0:
                break
        except KeyboardInterrupt as e:
            #kill_child_processes(parent_pid = current_pid)
            kill_all_processes()
            pass
        except Exception as e:
        #except (KeyboardInterrupt, Exception) as e:
            try:
                print(rank)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                print((''.join('!! ' + line for line in lines)))
                sys.stdout.flush()
            except Exception:
                pass

            signal.alarm(0)
            if log_f:
                log_f.close()
            status = 'process %-4d task %s/%s raised an Exception %s when visiting [%d].' % (process_index, task_id+1, length, type(e), rank)
            status_queue.put([process_index, status])
            string = '%s\t%s' % (getlocaltime(), status)
            if not isinstance(e, WebDriverException) and not isinstance(e, TimeoutException) and not isinstance(e, http.client.CannotSendRequest) and not isinstance(e, FunctionTimeoutException) and not isinstance(e, NavigationStuckException) and not isinstance(e, http.client.BadStatusLine):
            #if not isinstance(e, TimeoutException) and not isinstance(e, httplib.CannotSendRequest) and not isinstance(e, FunctionTimeoutException) and not isinstance(e, NavigationStuckException) and not isinstance(e, httplib.BadStatusLine):
                try:
                    print(string)
                    print(rank)
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                    print((''.join('!! ' + line for line in lines)))
                    sys.stdout.flush()
                except Exception:
                    pass
            if isinstance(e, IOError):
                kill_all_processes()
            if rank not in rank2fail_num:
                rank2fail_num[rank] = 1
            else:
                #if isinstance(e, WebDriverException):
                #    rank2fail_num[rank] += 0.5
                #else:
                #    rank2fail_num[rank] += 1
                if isinstance(e, TimeoutException) or isinstance(e, FunctionTimeoutException):
                    rank2fail_num[rank] += 1
                else:
                    rank2fail_num[rank] += 0.5
            if rank2fail_num[rank] >= 1:
                # we need to add the failed rank to processed_list.
                # otherwise, the while loop won't terminate
                processed_list.add(rank)
                log_f = open(log_file, 'a')
                status = 'failed'
                l = '%s\t%d\t%s\t%s\n' % (getlocaltime(), rank, domain, status)
                log_f.write(l)
                log_f.close()
                status = 'process %-4d task %s/%s failed to visit [%d].' % (process_index, task_id+1, length, rank)
                status_queue.put([process_index, status])
            if browser is not None:
                close_browser(browser)
            browser = None
    try:
        if browser is not None:
            close_browser(browser)
        gone, alive = kill_child_processes(parent_pid = current_pid)
        process_name = 'user-data-dir=%s' % (user_dir)
        kill_processes_by_name(process_name)
        process_name = 'log-path=webdriver_%s.log' % (user_dir)
        kill_processes_by_name(process_name)
    except (KeyboardInterrupt, Exception) as e:
        if not isinstance(e, KeyboardInterrupt):
            print(e)
    status = 'process %-4d task %s/%s pid [%d] completed.' % (process_index, task_id+1, length, current_pid)
    status_queue.put([process_index, status])
    #print(status)
    prepare_profile(user_dir=user_dir, remove_only=True)

def function_timeout_handler(sig, frame):
    raise FunctionTimeoutException("function timeouted!")

def signal_term_handler(sig, frame):
    global parent_pid
    current_pid = os.getpid()
    if current_pid == parent_pid:
        #msg = '%s\tparent process [%d] received sigterm!!! killing all child processes...\n' % (current_time, current_pid)
        process_name = 'chrome'
        kill_processes_by_name(process_name)
    kill_all_processes()

def kill_all_processes(restart_parent_flag=False):
    global parent_pid, process_list, log_f
    current_time = getlocaltime()
    current_pid = os.getpid()
    if current_pid == parent_pid:
        msg = '%s\tparent process [%d] received sigterm!!! killing all child processes...\n' % (current_time, current_pid)
    else:
        msg = '%s\tprocess [%d] received sigterm!!! killing all child processes... parent pid=[%d]\n' % (current_time, current_pid, parent_pid)
    #print(msg)
    #sys.stdout.flush()
    log_f.write(msg)
    kill_child_processes(parent_pid = current_pid)
    current_time = getlocaltime()
    msg = '%s\tall child processes of process [%d] are killed!!!\n' % (current_time, current_pid)
    log_f.write(msg)
    if current_pid == parent_pid:
        if restart_parent_flag:
            restart_all_tasks(log_f)
        else:
            log_f.close()
    sys.exit()

def main(argv):
    global rank2domain, input_type, access_control, find_sub_pages_script, get_max_size_script, fetch_doc_log_script, fire_events_script, num_instances, parent_pid, process_list, log_f, log_dir, script_dir, fetch_asg_logs_script, chrome_newtab_url, about_blank_url, chrome_extension_prefix, chrome_extension_suffix, rank, config_dir, log_pass, p_mode

    signal.signal(signal.SIGTERM, signal_term_handler)
    start_time = time.time()
    try:
        opts, args = getopt.getopt(argv, 'hu:d:i:n:p:t:s:e:c:l:', ['help', 'user_dir=', 'log_dir=', 'num=', 'process=', 'type=', 'input_file=', 'start=', 'end=', 'config_dir=', 'policy_mode=', 'log_pass='])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    user_dir = None
    access_control = True
    input_type = 'domain'
    input_file = 'top-1m.csv'

    num_instances = 512
    maximum_process_num = 8 # Change to 1 for debugging purposeF
    start = 0
    end = None
    config_dir = None
    log_pass = 0
    p_mode = 0 # url-level policies
    exp_dir = "exps"
    log_dir = "/data/local/public/dom_exp_data/dom_logs" # gpu6
    log_dir = "/data/dom_exp_data/dom_logs"
    for opt, arg in opts:
        if opt in ('-u', '--user_dir'):
            user_dir = arg
        elif opt in ('-d', '--dir'):
            log_dir = arg
        elif opt in ('-i', '--input_file'):
            input_file = arg
        elif opt in ('-n', '--num'):
            num_instances = int(arg)
        elif opt in ('-p', '--process'):
            maximum_process_num = int(arg)
        elif opt in ('-t', '--type'):
            input_type = arg
        elif opt in ('-s', '--start'):
            start = int(arg)
        elif opt in ('-e', '--end'):
            end = int(arg)
        elif opt in ('-c', '--config_dir'):
            config_dir = arg
        elif opt in ('-m', '--policy_mode'):
            p_mode = arg
        elif opt in ('-l', '--log_pass'):
            log_pass = int(arg)
        elif opt in ('-h', '--help'):
            usage()
            sys.exit(0)
    if user_dir is None or config_dir is None :
        usage()
        sys.exit(0)


    extract = tldextract.TLDExtract(include_psl_private_domains=True)
    try:
        os.mkdir(exp_dir)
    except OSError as e:
        pass
    try:
        os.mkdir(log_dir)
    except OSError as e:
        pass

    parent_pid = os.getpid()
    script_dir = os.getcwd()
    restart_parent_flag = False

    log_dir = os.path.join(script_dir, log_dir)
    log_file = 'exp_%s.log' % (user_dir)
    log_file = os.path.join(log_dir, log_file)
    log_f = codecs.open(log_file, encoding='utf-8', mode='a')
    current_time = getlocaltime()
    status = "PARENT SCRIPT STARTED! PARENT PID=[%d]" % parent_pid
    string = '%s\t%s\n' % (current_time, status)
    print(string)
    log_f.write(string)
    string = "%s\tProcess started, argv=%s\n" % (current_time, argv)
    log_f.write(string)

    completed_list = set()
    completion_reg = re.compile('Process [0-9\s]+task ([0-9]+)/[0-9]+ PID \[\d+\] completed.')
    with codecs.open(log_file, encoding='utf-8', mode='r') as input_f:
        for line in input_f:
            match = re.search(completion_reg, line)
            if match:
                task = int(match.group(1)) - 1
                completed_list.add(task)
    completed_list = set()

    input_f = open(input_file, 'r')
    lines = input_f.read().split('\n')[:-1]
    input_f.close()
    rank2domain = dict()
    for line in lines:
        data = line.split(',')
        rank = data[0]
        rank = int(rank)
        url = ','.join(data[1:])
        rank2domain[rank] = url
    if end is None:
        end = len(rank2domain)

    try:
        os.chdir(exp_dir)
    except OSError as e:
        pass

    # Remove temp files
    gc_chrome_tmp_files(force=True)

    process_name = 'chrome'
    kill_processes_by_name(process_name)

    tasks = [i for i in range(num_instances-1, -1, -1)]
    status_queue = Queue()
    try:
        length = len(tasks)
        head = 'Preparing [%d] task ...' % (length)
        final_status_set = set()
        progress = dict()
        for j in range(maximum_process_num, 0, -1):
            progress[j] = ''
        id_pool = [j for j in range(maximum_process_num, 0, -1)]
        process_num = 0
        process2status = dict()
        running_processes = set()
        process2id = dict()
        process2index = dict()
        process2start_time = dict()
        id2index = dict()
        id2task = dict()
        index2task = dict()
        round_num = 0
        process_list = list()
        killed_process_list = list()
        dead_num = 0
        dead_ratio = 0
        alive_check_timeout = 60
        dead_ratio_list = []
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
                try:
                    process_list.append(Task(target=measure, args=(user_dir_group, task, length, start, end, status_queue, process_index)))
                    process = process_list[-1]
                    process.start()
                except OSError as e:
                    tasks.append(group)
                    time.sleep(5)
                    continue
                process_num += 1
                running_processes.add(process)
                process2index[process] = process_index
                process2start_time[process] = time.time()
                index2task[process_index] = task

                current_time = getlocaltime()
                process_status = 'Process %-4d task %d/%d created. PID=%d ...' % (process_index, task+1, length, process.pid)
                string = '%s\t%s' % (current_time, process_status)
                print(string)
                sys.stdout.flush()
                if process_num % 20 == 0:
                    break
                #break

            #time.sleep(1)
            flag = False
            while any(process.is_alive() for process in process_list):
                time.sleep(1)
                current_time = getlocaltime()
                alive_count += 1
                num_alive_processes = sum(1 for process in process_list if process.is_alive())

                #flag = False
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

                    gc_chrome_tmp_files()
                    current_timestamp = time.time()
                    elapse = current_timestamp - start_time
                    dead_num = 0
                    # We need to get a list. Otherwise, we will receive an Exception: RuntimeError: Set changed size during iteration
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

                        # Start checking log file modification time after 10 minutes
                        if elapse >= 60*10:
                            process_start_time = process2start_time[process]
                            process_elapse = current_timestamp - process_start_time
                            user_dir_group = '%s_%d' % (user_dir, group)
                            user_dir_log_file = '%s.log' % (user_dir_group)
                            user_dir_log_file = os.path.join(log_dir, user_dir_log_file)
                            #mtime = current_timestamp
                            ctime = current_timestamp
                            try:
                                #mtime = os.path.getmtime(user_dir_log_file) # https://docs.python.org/2/library/os.path.html#os.path.getmtime
                                ctime = os.path.getctime(user_dir_log_file) # https://docs.python.org/2/library/os.path.html#os.path.getctime
                            except OSError as e:
                                pass
                            if current_timestamp - ctime >= 60*10 and process_elapse >= 60*5:
                                dead_num += 1
                                process_status = 'Process %-4d task %d/%d PID [%d] seems to be dead. Terminating and restarting process...' % (process_index, group+1, length, process.pid)
                                string = '%s\t%s\n' % (current_time, process_status)
                                log_f.write(string)
                                gone, alive = kill_child_processes(parent_pid = process.pid)
                                process_name = 'user-data-dir=%s' % (user_dir_group)
                                kill_processes_by_name(process_name)
                                process_name = 'log-path=webdriver_%s.log' % (user_dir_group)
                                kill_processes_by_name(process_name)

                                running_processes.remove(process)
                                tasks.append(group)
                                flag = True
                                current_timestamp = time.time()
                    dead_ratio = 1.0 * dead_num / maximum_process_num
                    if len(dead_ratio_list) >= 5:
                        dead_ratio_list.pop(0)
                    dead_ratio_list.append(dead_ratio)
                    avg_dead_ratio = np.mean(dead_ratio_list)
                    if avg_dead_ratio >= 0.1:
                        status = "Too many tasks are dead! Average dead ratio is %.2f!" % (avg_dead_ratio)
                        string = '%s\t%s\n' % (current_time, status)
                        print(string)
                        log_f.write(string)
                        raise TooManyTasksDead("Too many tasks are dead! Average dead ratio is %.2f!" % (avg_dead_ratio))
                if flag == True or (num_alive_processes < maximum_process_num and (len(tasks) > 0 or alive_count % alive_check_timeout == 0)):
                    break
            # We need to get a list. Otherwise, we will receive an Exception: RuntimeError: Set changed size during iteration
            #for process in list(running_processes):
            for process in process_list:
                if not process.is_alive():
                    if process in running_processes:
                        running_processes.remove(process)

    except (KeyboardInterrupt, Exception) as e:
        current_time = getlocaltime()
        status = "PARENT SCRIPT Exception %s" % type(e)
        string = '%s\t%s\n' % (current_time, status)
        log_f.write(string)
        if not isinstance(e, KeyboardInterrupt) and not isinstance(e, TooManyTasksDead):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print((type(e), "PARENT"))
            print((''.join('!! ' + line for line in lines)))
            status = ''.join('!! ' + line for line in lines)
            string = '%s\t%s\n' % (current_time, status)
            log_f.write(string)
        restart_parent_flag = isinstance(e, TooManyTasksDead)
        if restart_parent_flag:
            os.chdir(script_dir)
        #process_name = 'chrome'
        #kill_processes_by_name(process_name)
        kill_all_processes(restart_parent_flag)


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

    gc_chrome_tmp_files()

    current_time = getlocaltime()
    status = "PARENT SCRIPT COMPLETED! PARENT PID=[%d]" % parent_pid
    string = '%s\t%s\n' % (current_time, status)
    log_f.write(string)
    log_f.close()

def usage():
    tab = '\t'
    print('Usage:')
    print((tab + 'python %s [OPTIONS]' % (__file__)))
    print((tab + '-d | --log_dir='))
    print((tab*2 + 'Log directory'))
    print((tab + '-u | --user_dir='))
    print((tab*2 + 'User directory of Chrome'))
    print((tab + '-i | --input_file='))
    print((tab*2 + 'Input file that contains URLs and ranks'))
    print((tab + '-n | --num='))
    print((tab*2 + 'Number of task splits, default is 512'))
    print((tab + '-p | --process='))
    print((tab*2 + 'Maximum number of processes, default is 8'))
    print((tab + '-t | --type'))
    print((tab*2 + 'Input type, [domain|url], default [domain]'))
    print((tab + '-s | --start'))
    print((tab*2 + 'Start index, default 0'))
    print((tab + '-e | --end'))
    print((tab*2 + 'End index, default number of URLs'))
    print((tab + '-c | --config_dir'))
    print((tab*2 + 'Directory of isolation policies'))
    print((tab + '-l | --log_pass'))
    print((tab*2 + 'Fallback context, use 1 for first-party context, 3 for third-party and 0 for clean browser'))
    print((tab + '-m | --policy_mode'))
    print((tab*2 + 'Isolation policy mode, use 1 for domain-level policies and 0 for URL-level policies'))



if __name__ == '__main__':
    main(sys.argv[1:])
