#!/bin/env python3

import os
import re
import subprocess
import unicodedata

LLD_JSON_PATH = '/var/local/hpsa_zabbix'
LLD_METRICS_PATH = '/var/local/hpsa_zabbix/metrics'  # Be careful all files in this directory deleted automatically.
LLD_CONTROLLERS = 'controllers.json'
LLD_ARRAYS = 'arrays.json'
LLD_DISKS = 'disks.json'

HPSSA = '/usr/sbin/hpssacli'  # full path to hpssacli

ARRAY_NAME_PATT = re.compile(r'Array:\s+(?P<array_name>.+)')
PD_NAME_PATT = re.compile(r'physicaldrive\s+(?P<pd_name>.+)$')


# Data processing pipe.
def pipe(data, *fseq):
    for fn in fseq:
        data = fn(data)
    return data


def debug(data):
    print(data)
    return data


def get_hpsa_config():
    """Function for running hpssacli and get detailed output about controllers."""
    cli = [HPSSA, 'ctrl', 'all', 'show', 'config', 'detail']
    p = subprocess.Popen(
        cli,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    (output, err) = p.communicate()
    if err:
        raise ValueError(f'hpsa call error {err}')
    return output


def create_dir(full_dir_path):
    if not os.path.exists(full_dir_path):
        os.makedirs(full_dir_path)


def remove_file(full_file_name):
    if os.path.exists(full_file_name):
        os.remove(full_file_name)


def remove_all_metrics_files(data):
    """Function to remove all files in LLD_METRICS_PATH directory."""
    if os.path.exists(LLD_METRICS_PATH):
        [os.remove(os.path.join(LLD_METRICS_PATH, _)) for _ in os.listdir(LLD_METRICS_PATH) if os.path.isfile(os.path.join(LLD_METRICS_PATH, _))]
    return data


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


##========= cut from https://opendev.org/x/proliantutils/src/branch/master/proliantutils/hpssa/objects.py
## Не хотелось добавлять зависимость из-за четырёх приватных функций. Код классный!

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


##==================== end cut from https://opendev.org/x/proliantutils/src/branch/master/proliantutils/hpssa/objects.py


def pretty_print(info_dict, level=0):
    """Recursive function for printing dictionary with hpssa detailed information."""

    indent = ' ' * 4
    current_level = level
    for k, v in info_dict.items():
        if isinstance(v, str) or v is None:
            print(f"{indent * current_level}{k}: {v}")
        else:
            print()
            print(f"{indent * current_level}{k}:")
            pretty_print(v, level=current_level + 1)


def lld_discovery_controllers(data):
    """Function for create LLD json with information about controllers."""

    file_ = LLD_CONTROLLERS
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    controllers = data.keys()
    json_data = ''
    for item in controllers:
        json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(item)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def lld_discovery_arrays(data):
    """Function for create LLD json with information about RAID arrays."""

    file_ = LLD_ARRAYS
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    json_data = ''
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(ctrl)}","' \
                                            f'{{#ARRAYNAME}}":"{clean_name(ar_name)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def lld_discovery_pds(data):
    """Function for create LLD json with information about RAID physical disks."""

    file_ = LLD_DISKS
    discovery_file = os.path.join(LLD_JSON_PATH, file_)
    create_dir(LLD_JSON_PATH)
    remove_file(discovery_file)
    json_data = ''
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for pd_key, pd_value in ar_value.items():
                        match2 = re.search(PD_NAME_PATT, pd_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            json_data = json_data + f'{{"{{#CTRLNAME}}":"{clean_name(ctrl)}","{{#ARRAYNAME}}":"' \
                                                    f'{clean_name(ar_name)}","{{#PDNAME}}":"{clean_name(pd_name)}"}},'
    json_data = json_data[:-1]
    with open(discovery_file, 'w') as fl:
        print(f'{{"data":[{json_data}]}}', file=fl)
    return data


def get_ctrl_metrics(data):
    """Function for create controllers metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        file_name = clean_name(ctrl)
        full_file_name = os.path.join(LLD_METRICS_PATH, file_name)
        with open(full_file_name, 'w') as fl:
            if isinstance(ctrl_value, dict):
                for metric, value in ctrl_value.items():
                    if isinstance(value, str):
                        print(f"{metric}={value}", file=fl)
    return data


def get_array_metrics(data):
    """Function for create RAID arrays metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    file_name = clean_name(f"{ctrl}__{ar_name}")
                    full_file_name = os.path.join(LLD_METRICS_PATH, file_name)
                    with open(full_file_name, 'w') as fl:
                        if isinstance(ar_value, dict):
                            for metric, value in ar_value.items():
                                if isinstance(value, str):
                                    print(f"{metric}={value}", file=fl)
    return data


def get_pd_metrics(data):
    """Function for create physical disks metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        if isinstance(ctrl_value, dict):
            for ar_key, ar_value in ctrl_value.items():
                match = re.search(ARRAY_NAME_PATT, ar_key)
                if match:
                    ar_name = match.groupdict()['array_name']
                    for pd_key, pd_value in ar_value.items():
                        match2 = re.search(PD_NAME_PATT, pd_key)
                        if match2:
                            pd_name = match2.groupdict()['pd_name']
                            file_name = clean_name(f"{ctrl}__{ar_name}__{pd_name}")
                            full_file_name = os.path.join(LLD_METRICS_PATH, file_name)
                            with open(full_file_name, 'w') as fl:
                                if isinstance(pd_value, dict):
                                    for metric, value in pd_value.items():
                                        if isinstance(value, str):
                                            print(f"{metric}={value}", file=fl)
    return data


def get_all_metrics(data):
    """Function for create all (controllers, arrays and disks) metrics files."""

    create_dir(LLD_METRICS_PATH)
    for ctrl, ctrl_value in data.items():
        ctrl_file_name = clean_name(ctrl)
        ctrl_full_file_name = os.path.join(LLD_METRICS_PATH, ctrl_file_name)
        with open(ctrl_full_file_name, 'w') as ctrl_fl:
            if isinstance(ctrl_value, dict):
                for ar_key, ar_value in ctrl_value.items():
                    arr_match = re.search(ARRAY_NAME_PATT, ar_key)
                    if arr_match:
                        ar_name = arr_match.groupdict()['array_name']
                        ar_file_name = clean_name(f"{ctrl}__{ar_name}")
                        ar_full_file_name = os.path.join(LLD_METRICS_PATH, ar_file_name)
                        with open(ar_full_file_name, 'w') as ar_fl:
                            for pd_key, pd_value in ar_value.items():
                                pd_match = re.search(PD_NAME_PATT, pd_key)
                                if pd_match:
                                    pd_name = pd_match.groupdict()['pd_name']
                                    pd_file_name = clean_name(f"{ctrl}__{ar_name}__{pd_name}")
                                    pd_full_file_name = os.path.join(LLD_METRICS_PATH, pd_file_name)
                                    with open(pd_full_file_name, 'w') as pd_fl:
                                        if isinstance(pd_value, dict):
                                            for metric, value in pd_value.items():
                                                if isinstance(value, str):
                                                    print(f"{metric}={value}", file=pd_fl)
                                if isinstance(pd_value, str):
                                    print(f"{pd_key}={pd_value}", file=ar_fl)
                    if isinstance(ar_value, str):
                        print(f"{ar_key}={ar_value}", file=ctrl_fl)
    return data


if __name__ == '__main__':
    pipe(
        get_hpsa_config(),
        _convert_to_dict,
        remove_all_metrics_files,
        # debug,
        lld_discovery_controllers,
        lld_discovery_arrays,
        lld_discovery_pds,
        #get_ctrl_metrics,
        #get_array_metrics,
        #get_pd_metrics
        get_all_metrics
        # pretty_print
    )
