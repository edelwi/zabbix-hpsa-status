#!/bin/env python3
# Получение статуса RAID массивов, утилитой hpssacli. Требуются root привилегии.
# в стиле функционального ядра. по мотивам https://m.habr.com/ru/post/555370/
import subprocess
import re
import os
import unicodedata

LLD_JSON_PATH = '/home/hpsa_zabbix'
LLD_METRICS_PATH = '/home/hpsa_zabbix/data'

# Конвейер обработки данных
def pipe(data, *fseq):
    for fn in fseq: 
        data = fn(data)
    return data

def debug(data):
    print(data)
    return data

def get_hpsa_config():
    hpsa_path = '/usr/sbin/hpssacli'

    cli = [hpsa_path, 'ctrl', 'all', 'show', 'config', 'detail' ]
    p = subprocess.Popen(
        cli,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    (output, err) = p.communicate()
    if err:
        raise ValueError(f'hpsa call error {err}')
    return output

def parse(output):

    ld_status_pat = re.compile(r'logicaldrive\s+(?P<ld_num>\d{1})\s+\([1-9\.]+\s+[G|T|P]B,\s+RAID\s+(?P<raid_num>\d{1,2}),\s+(?P<ld_status>.+)\)$', re.X)
    pd_status_pat = re.compile(r'physicaldrive\s+.+\s+\(port\s+(?P<port>.+):box\s+(?P<box>\d+):bay\s+(?P<bay>\d+),\s+(?P<interface>.+),\s+(?P<size>\d+)\s+(?P<size_suffix>[M|G|T|P]B),\s+(?P<status>.+)\)$', re.X)

    ld = []
    pd = []
    text = output.decode('utf-8').split('\n')
    #print(output, type(output))
    for line in text:
        match = re.search(ld_status_pat, line)
        #print(line, match)
        if match:
            ld.append(match.groupdict())
            #print(match.groupdict())
        match2 = re.search(pd_status_pat, line)
        if match2:
            pd.append(match2.groupdict())
            #print(match2.groupdict())
    return ld, pd
    

# from https://stackoverflow.com/questions/4814040/allowed-characters-in-filename
def clean_name(name, replace_space_with=None):
    """
    Remove invalid file name chars from the specified name

    :param name: the file name
    :param replace_space_with: if not none replace space with this string
    :return: a valid name for Win/Mac/Linux
    """

    # ref: https://en.wikipedia.org/wiki/Filename
    # ref: https://stackoverflow.com/questions/4814040/allowed-characters-in-filename
    # No control chars, no: /, \, ?, %, *, :, |, ", <, >

    # remove control chars
    name = ''.join(ch for ch in name if unicodedata.category(ch)[0] != 'C')

    cleaned_name = re.sub(r'[/\\?%*:|"<>]', '_', name)
    if replace_space_with is not None:
        return cleaned_name.replace(' ', replace_space_with)
    return cleaned_name


##========= from https://opendev.org/x/proliantutils/src/branch/master/proliantutils/hpssa/objects.py
## Не хотелось добавлять зависимость из-за четырёх функций. Код классный!

def _get_indentation(string):
    """Return the number of spaces before the current line."""
    return len(string) - len(string.lstrip(' '))


def _get_key_value(string):
    """Return the (key, value) as a tuple from a string."""
    # Normally all properties look like this:
    #   Unique Identifier: 600508B1001CE4ACF473EE9C826230FF
    #   Disk Name: /dev/sda
    #   Mount Points: None
    key = ''
    value = ''
    try:
        key, value = string.split(': ')
    except ValueError:
        # This handles the case when the property of a logical drive
        # returned is as follows. Here we cannot split by ':' because
        # the disk id has colon in it. So if this is about disk,
        # then strip it accordingly.
        #   Mirror Group 0: physicaldrive 6I:1:5
        string = string.lstrip(' ')
        if string.startswith('physicaldrive'):
            fields = string.split(' ')
            # Include fields[1] to key to avoid duplicate pairs
            # with the same 'physicaldrive' key
            key = fields[0] + " " + fields[1]
            value = fields[1]
        else:
            # TODO(rameshg87): Check if this ever occurs.
            return string.strip(' '), None

    return key.strip(' '), value.strip(' ')

def _get_dict(lines, start_index, indentation, deep):
    """Recursive function for parsing hpssacli/ssacli output."""

    info = {}
    current_item = None

    i = start_index
    while i < len(lines):

        current_line = lines[i]
        current_line_indentation = _get_indentation(current_line)

        # Check for multi-level returns
        if current_line_indentation < indentation:
            return info, i - 1

        if current_line_indentation == indentation:
            current_item = current_line.lstrip(' ')
            info[current_item] = {}
            i = i + 1
            continue

        if i < len(lines) - 1:
            next_line_indentation = _get_indentation(lines[i + 1])
        else:
            next_line_indentation = current_line_indentation

        if next_line_indentation > current_line_indentation:
            ret_dict, i = _get_dict(lines, i,
                                    current_line_indentation, deep + 1)
            for key in ret_dict.keys():
                if key in info[current_item]:
                    info[current_item][key].update(ret_dict[key])
                else:
                    info[current_item][key] = ret_dict[key]
        else:
            key, value = _get_key_value(current_line)
            if key:
                info[current_item][key] = value

        # Do not return if it's the top level of recursion
        if next_line_indentation < current_line_indentation and deep > 0:
            return info, i

        i = i + 1

    return info, i

def _convert_to_dict(stdout):
    """Wrapper function for parsing hpssacli/ssacli command.
    This function gets the output from hpssacli/ssacli command
    and calls the recursive function _get_dict to return
    the complete dictionary containing the RAID information.
    """

    lines = stdout.decode('utf-8').split("\n")
    lines = list(filter(None, lines))
    info_dict, j = _get_dict(lines, 0, 0, 0)
    return info_dict    

##==================== from https://opendev.org/x/proliantutils/src/branch/master/proliantutils/hpssa/objects.py


def print_out(params):
    for param in params:
        [print(_) for _ in param]
        
def prety_print(info_dict, level=0):
    indent = ' ' * 4
    current_level = level
    for k,v in info_dict.items():
        if isinstance(v, str) or v is None:
            print(f"{indent*current_level}{k}: {v}")
        else:
            print()
            print(f"{indent*current_level}{k}:")
            prety_print(v, level=current_level+1)


def lld_discovery_controllers(data):
    file_ = 'controllers.json'
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    if not os.path.exists(LLD_JSON_PATH):
        os.makedirs(LLD_JSON_PATH)
    if os.path.exists(discovery_file) and os.path.isfile(discovery_file):
        # Удалим старые данные, если обнаружение сломается пусть заббикс об этом узнает
        os.remove(discovery_file)
    controllers = data.keys()
    json_start = '{"data":['
    json_end = ']}'
    json_data = ''
    for item in controllers:
        json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(item)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{json_start}{json_data}{json_end}', file=fl)
    return data
    
def lld_discovery_arrays(data):
    arr_name_patt = re.compile(r'Array:\s+(?P<array_name>.+)')
    file_ = 'arrays.json'
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    if not os.path.exists(LLD_JSON_PATH):
        os.makedirs(LLD_JSON_PATH)
    if os.path.exists(discovery_file) and os.path.isfile(discovery_file):
        # Удалим старые данные, если обнаружение сломается пусть заббикс об этом узнает
        os.remove(discovery_file)
    controllers = data.keys()
    json_start = '{"data":['
    json_end = ']}'
    json_data = ''
    for conrtiller,value in data.items():
        if isinstance(value, dict):
            for ctrl_key, ctrl_value in value.items():
                match = re.search(arr_name_patt, ctrl_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(conrtiller)}","{{#ARRAYNAME}}":"{clean_name(ar_name)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{json_start}{json_data}{json_end}', file=fl)
    return data
    

def lld_discovery_pds(data):
    arr_name_patt = re.compile(r'Array:\s+(?P<array_name>.+)')
    pd_name_patt = re.compile(r'physicaldrive\s+(?P<pd_name>.+)$')
    file_ = 'disks.json'
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    if not os.path.exists(LLD_JSON_PATH):
        os.makedirs(LLD_JSON_PATH)
    if os.path.exists(discovery_file) and os.path.isfile(discovery_file):
        # Удалим старые данные, если обнаружение сломается пусть заббикс об этом узнает
        os.remove(discovery_file)
    controllers = data.keys()
    json_start = '{"data":['
    json_end = ']}'
    json_data = ''
    for conrtiller,value in data.items():
        if isinstance(value, dict):
            for ctrl_key, ctrl_value in value.items():
                match = re.search(arr_name_patt, ctrl_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for arr_key, arr_val in ctrl_value.items():
                        match2 = re.search(pd_name_patt, arr_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(conrtiller)}","{{#ARRAYNAME}}":"{clean_name(ar_name)}","{{#PDNAME}}":"{clean_name(pd_name)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{json_start}{json_data}{json_end}', file=fl)
    return data


def get_ctrl_metrics(data):
    if not os.path.exists(LLD_METRICS_PATH):
        os.makedirs(LLD_METRICS_PATH)
    for ctrl,ctrl_val in data.items():
        fname = clean_name(ctrl)
        full_fname = os.path.join(LLD_METRICS_PATH, fname)
        if os.path.exists(full_fname) and os.path.isfile(full_fname):
            os.remove(full_fname)
        with open(full_fname, 'w') as fl:
            if isinstance(ctrl_val, dict):
                for metric,value in ctrl_val.items():
                    if isinstance(value, str):
                        print(f"{metric}={value}", file=fl)
    return data


def get_array_metrics(data):
    arr_name_patt = re.compile(r'Array:\s+(?P<array_name>.+)')
    if not os.path.exists(LLD_METRICS_PATH):
        os.makedirs(LLD_METRICS_PATH)
    for conrtiller,value in data.items():
        if isinstance(value, dict):
            for ctrl_key, ctrl_value in value.items():
                match = re.search(arr_name_patt, ctrl_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    fname = clean_name(f"{conrtiller}__{ar_name}")
                    full_fname = os.path.join(LLD_METRICS_PATH, fname)
                    if os.path.exists(full_fname) and os.path.isfile(full_fname):
                        os.remove(full_fname)
                    with open(full_fname, 'w') as fl:
                        if isinstance(ctrl_value, dict):
                            for metric, value in ctrl_value.items():
                                if isinstance(value, str):
                                    print(f"{metric}={value}", file=fl)
    return data



def get_pd_metrics(data):
    arr_name_patt = re.compile(r'Array:\s+(?P<array_name>.+)')
    pd_name_patt = re.compile(r'physicaldrive\s+(?P<pd_name>.+)$')
    if not os.path.exists(LLD_METRICS_PATH):
        os.makedirs(LLD_METRICS_PATH)
    for conrtiller,value in data.items():
        if isinstance(value, dict):
            for ctrl_key, ctrl_value in value.items():
                match = re.search(arr_name_patt, ctrl_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for arr_key, arr_value in ctrl_value.items():
                        match2 = re.search(pd_name_patt, arr_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            fname = clean_name(f"{conrtiller}__{ar_name}__{pd_name}")
                            full_fname = os.path.join(LLD_METRICS_PATH, fname)
                            if os.path.exists(full_fname) and os.path.isfile(full_fname):
                                os.remove(full_fname)
                            with open(full_fname, 'w') as fl:
                                if isinstance(arr_value, dict):
                                    for metric, value in arr_value.items():
                                        if isinstance(value, str):
                                            print(f"{metric}={value}", file=fl)
    return data

if __name__ == '__main__':
    pipe(
        get_hpsa_config(), 
        #parse,
        _convert_to_dict,
        #debug,
        #print_out,
        lld_discovery_controllers,
        lld_discovery_arrays,
        lld_discovery_pds,
        get_ctrl_metrics,
        get_array_metrics,
        get_pd_metrics
        #prety_print
        )

