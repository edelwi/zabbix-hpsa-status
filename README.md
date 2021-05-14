# zabbix-hpsa-status

Zabbix Template and python script with Low Level Discovery (LLD) for HP SmartArray controllers.

## Prerequisites:

    - HPSSACLI
    - python 3.6
    - Zabbix 5

## Installation:

    - Add checkraid.py to the cron (* * * * * python3 /path/to/zabbix-hpsa-status/checkraid.py  # require root privileges).
    - Import template hpsa_status_template_zabbix5.xml to the Zabbix.
    - Add Template HP Smart Array Status to appropriate server.
    - Change selinux context for the LLD_JSON_PATH and LLD METRICS_PATH directories or disable it at all.

### Supported Controllers (depends on hpssacli):

- Dynamic Smart Array B110i SATA RAID
- Smart Array P212 Controller
- Smart Array P410 Controller
- Smart Array P410i Controller
- Smart Array P411 Controller
- Smart Array P711m Controller
- Smart Array P712m Controller
- Smart Array P812 Controller

- Dynamic Smart Array B120i
- Dynamic Smart Array B320i
- Smart Array P220i Controller
- Smart Array P222 Controller
- Smart Array P420 Controller
- Smart Array P420i Controller
- Smart Array P421 Controller
- Smart Array P721m Controller
- Smart Array P822 Controller

- Smart Array P230i Controller
- Smart Array P430 Controller
- Smart Array P431 Controller
- Smart Array P530 Controller
- Smart Array P531 Controller
- Smart Array P731m Controller
- Smart Array P830 Controller
- Smart Array P830i Controller

- Dynamic Smart Array B140i
- Smart HBA H240 Controller
- Smart HBA H240ar Controller
- Smart HBA H241 Controller
- Smart HBA H244br Controller
- Smart Array P244br Controller
- Smart Array P246br Controller
- Smart Array P440 Controller
- Smart Array P440ar Controller
- Smart Array P441 Controller
- Smart Array P741m Controller
- Smart Array P840 Controller
- Smart Array P841 Controller

## Tested on:

    - Smart Array P840
    - HPSSA 2.40
    - CentOS Linux release 8.3.2011
    - Python 3.8.3
    - Zabbix 5.0.7