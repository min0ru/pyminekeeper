import datetime
import json
import os
import subprocess
import time
import urllib.request
from multiprocessing import Process


def kill(pid):
    """
    Using Windows TASKKILL command to force kill process with all of it's childrens.
    General Process.terminate() will not work because it's not finishing all childrens
    even in daemon mode :(
    Alternative is to use psutil crossplatform library.
    :param pid: process id to kill.
    :return: None
    """
    subprocess.Popen("TASKKILL /F /PID {pid} /T".format(pid=pid))


def miner_process_function(miner_exe_path, new_window=True):
    """
    Miner process function.
    Starts executable on miner_path
    :param miner_exe_path: executable path to run.
    :return: None
    """
    base_dir = os.path.dirname(miner_exe_path)
    if base_dir:
        os.chdir(os.path.dirname(miner_exe_path))
    print('Subprocess starts "{}"'.format(miner_exe_path))
    child = subprocess.Popen(miner_exe_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
    print('Started new console process with pid {}'.format(child.pid))
    child.wait()
    print('Subprocess exits')


def start_miner(miner_path):
    """
    Function creates new child process in daemon mode.
    :param miner_path: executable path to run.
    :return: miner process
    """
    miner_process = Process(target=miner_process_function, args=(miner_path,))
    miner_process.start()
    return miner_process


def api_url(api_params):
    """
    Get miner url for hashrate monitor api
    :param host: host address
    :param port: port
    :param page: page
    :param user: http basic auth user
    :param password: http basic auth password
    :return:
    """
    user = api_params.get('user', None)
    password = api_params.get('password', None)
    host = api_params.get('host', 'localhost')
    port = api_params.get('port', 80)
    page = api_params.get('page', '')

    if user and password:
        url = 'http://{}:{}@{}:{}/{}'.format(user, password, host, port, page)
    else:
        url = 'http://{}:{}/{}'.format(host, port, page)
    return url


def get_json_data(url):
    """
    Load JSON data from given url
    :param url: full miner json api url
    :return: 
    """
    # TODO add http basic auth support
    response = urllib.request.urlopen(url)
    if response.code != 200:
        return None
    json_data = json.loads(response.read())
    return json_data


def get_hashrate(api_params):
    """
    Request load and parse miner hashrate from specified api
    :param api_params: dictionary, contains all information about api
    :return: current total hashrate or -1 on error
    """
    miner_status_data = None
    url = api_url(api_params)

    if api_params.get('type') == 'JSON':
        try:
            miner_status_data = get_json_data(url)
        except:
            return -1

    if not miner_status_data:
        return -1

    parse_function = api_params['parse_function']
    try:
        hashrate = parse_function(miner_status_data)
    except:
        return -1
    return hashrate


def parse_castxmr_hashrate(status_data):
    """
    Function getting Cast XMR miner hashrate via HTTP_JSON miner api.

    Cast XMR JSON example:

    {
        "total_hash_rate": 2000000,
        "total_hash_rate_avg": 2000000,
        "pool": {
            "server": "etn-eu2.nanopool.org:13333",
            "status": "connected",
            "online": 1061,
            "offline": 0,
            "reconnects": 0,
            "time_connected": "2017-12-10 19:45:45",
            "time_disconnected": "2017-12-10 19:45:45"
        },
        "job": {
            "job_number": 27,
            "difficulty": 120001,
            "running": 55,
            "job_time_avg": 38.69
        },
        "shares": {
            "num_accepted": 42,
            "num_rejected": 0,
            "num_invalid": 0,
            "num_network_fail": 0,
            "num_outdated": 6,
            "search_time_avg": 33.86
        },
        "devices": [
        {
            "device": "GPU0",
            "device_id": 0,
            "hash_rate": 1000000,
            "hash_rate_avg": 1000000,
            "gpu_temperature": 42,
            "gpu_fan_rpm": 9999
        },
        {
            "device": "GPU1",
            "device_id": 1,
            "hash_rate": 1000000,
            "hash_rate_avg": 1000000,
            "gpu_temperature": 42,
            "gpu_fan_rpm": 9999
        }
        ]
    }

    :param host: miner http host address.
    :param port: miner http port.
    :return: current miner hashrate or -1 in case of error.
    """
    hashrate = status_data.get('total_hash_rate', -1)
    return hashrate


def parse_xmrstak_hashrate(status_data):
    """

    XMR Stak JSON example:

    {
       "version":"xmr-stak/2.0.0/0005e4a/master/win/nvidia-amd-cpu/aeon-monero/20",
       "hashrate":{
          "threads":[
             [
                616.4,
                null,
                null
             ],
             [
                605.9,
                null,
                null
             ]
          ],
          "total":[
             1222.3,
             null,
             null
          ],
          "highest":1229.3
       },
       "results":{
          "diff_current":120001,
          "shares_good":0,
          "shares_total":0,
          "avg_time":0.0,
          "hashes_total":0,
          "best":[
             0,0,0,0,0,0,0,0,0,0
          ],
          "error_log":[
          ]
       },
       "connection":{
          "pool":"etn-eu1.nanopool.org:13333",
          "uptime":55,
          "ping":0,
          "error_log":[
             {
                "last_seen":1512946470,
                "text":"[etn-us-west1.nanopool.org::13333] CONNECT error: GetAddrInfo: Error description. "
             }
          ]
       }
    }

    :return:
    """

    # TODO: Fix encoding error in connection error message

    try:
        hashrate_info = status_data.get('hashrate', None)
        if not hashrate_info:
            return -1
        hashrate = hashrate_info.get('total', None)[0]
        if not hashrate:
            return -1
    except:
        return -1
    return hashrate


def run_time_ended(last_start_time, max_run_time_minutes=30):
    """
    Checking if miner run out of running time
    :param last_start_time: last miner start time.
    :param max_run_time_minutes: miner running time.
    :return: Boolean indicates if miner should be restarted.
    """
    current_run_time_minutes = (datetime.datetime.now() - last_start_time).seconds * 60
    if current_run_time_minutes > max_run_time_minutes:
        return True
    return False


def miner_keeper():
    """
    Function running miner and tracks it's process status, hashrate etc.
    Miner restarts periodically with max_run_time_minutes interval.
    :return: None
    """

    # TODO: move me into settings.py / json
    cold_start_scripts = [
        r'C:\miners\tools\devcon\devcon.exe disable "PCI\VEN_1002&DEV_687F"',
        r'C:\miners\tools\devcon\devcon.exe enable "PCI\VEN_1002&DEV_687F"',
        r'C:\miners\tools\overdriventool\OverdriveNTool.exe -p1vega1100_900_905 -p2vega1100_900_905 -p3vega1100_900_905"',
    ]
    colds_start_sleep_interval = 5
    miner_exe_path = r'C:\miners\xmr-stak\xmr-stak.exe'
    target_hashrate = 1100
    hot_restart_interval_minutes = 5
    max_run_time_minutes = 2
    initial_sleep_time_minutes = 1
    check_interval_seconds = 10
    process_exit_time_seconds = 5


    # xmr-stak api
    xmr_stak_api = {
        'type': 'JSON',
        'user': '',
        'password': '',
        'host': '127.0.0.1',
        'port': 4580,
        'page': 'api.json',
        'parse_function': parse_xmrstak_hashrate,
    }

    # cast xmr api
    cast_xmr_api = {
        'type': 'JSON',
        'user': '',
        'password': '',
        'host': '127.0.0.1',
        'port': 7777,
        'page': '',
        'parse_function': parse_castxmr_hashrate,
    }

    hashrate_api_params = xmr_stak_api

    last_start_time = None

    while True:

        if not last_start_time:
            cold_start_needed = True
            print('First start in current session. Launching cold start scripts.')
        elif (datetime.datetime.now() - last_start_time).seconds < hot_restart_interval_minutes * 60:
            cold_start_needed = True
            print('Last restart was less then {} minutes ago. Launching cold start scripts.'
                  .format(hot_restart_interval_minutes))
        else:
            cold_start_needed = False
            print('Hot restarting miner')

        if cold_start_needed:
            for cold_start_script in cold_start_scripts:
                print('Running: "{}"'.format(cold_start_script))
                subprocess.Popen(cold_start_script)
                time.sleep(colds_start_sleep_interval)

        print('Running miner for {} minutes'.format(max_run_time_minutes))
        miner_process = start_miner(miner_exe_path)
        last_start_time = datetime.datetime.now()
        print('Miner started pid {}. Sleeping for {} minutes to stabilize hashrate before checks'
              .format(miner_process.pid, initial_sleep_time_minutes))
        time.sleep(initial_sleep_time_minutes * 60)
        hashrate_ok = True

        while run_time_ended(last_start_time, max_run_time_minutes) and hashrate_ok:
            time.sleep(check_interval_seconds)

            if not miner_process.is_alive():
                print('Miner process is dead! Restarting!')
                break

            current_hashrate = get_hashrate(hashrate_api_params)
            if current_hashrate <= 0:
                hashrate_ok = False
                print('Error in getting miner hashrate! Restarting miner!')
            elif current_hashrate < target_hashrate:
                hashrate_ok = False
                print('Error! Current hashrate {} is lower than target {}. Restarting miner!'
                      .format(current_hashrate, target_hashrate))
            else:
                print('[OK] Miner hashrate: {} is above target hashrate {}!'
                      .format(current_hashrate, target_hashrate))

        if miner_process.is_alive():
            print('Killing miner process.')
            kill(miner_process.pid)
            print('Waiting process to exit.')
            time.sleep(process_exit_time_seconds)


def main():
    miner_keeper()

if __name__ == '__main__':
    main()

